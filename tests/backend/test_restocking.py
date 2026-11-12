"""
Tests for restocking API endpoints (recommendations and restock orders).
"""
from datetime import datetime, timedelta

import pytest

import main

TREND_RANK = {"increasing": 0, "stable": 1, "decreasing": 2}


@pytest.fixture(autouse=True)
def reset_restock_orders():
    """Restock orders live in memory; clear them so each test starts clean."""
    main.restock_orders.clear()
    yield
    main.restock_orders.clear()


def get_recommendations(client, budget):
    response = client.get(f"/api/restock-recommendations?budget={budget}")
    assert response.status_code == 200
    return response.json()


class TestRestockRecommendations:
    """Test suite for the restock recommendations endpoint."""

    def test_get_recommendations_structure(self, client):
        """Test the recommendation response structure."""
        data = get_recommendations(client, 25000)

        for field in ["budget", "total_cost", "remaining_budget", "total_needed_cost", "items"]:
            assert field in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0

        for item in data["items"]:
            for field in ["sku", "name", "category", "trend", "needed_quantity",
                          "recommended_quantity", "unit_cost", "line_total",
                          "lead_time_days", "priority", "on_hand", "on_order"]:
                assert field in item
            assert isinstance(item["recommended_quantity"], int)
            assert 0 <= item["recommended_quantity"] <= item["needed_quantity"]
            assert item["lead_time_days"] > 0

    def test_recommendations_stay_within_budget(self, client):
        """Test that the recommended total never exceeds the budget."""
        for budget in [0, 100, 5000, 25000, 60000]:
            data = get_recommendations(client, budget)
            assert data["total_cost"] <= budget + 0.001
            assert abs(data["remaining_budget"] - (budget - data["total_cost"])) < 0.01

    def test_recommendations_line_total_calculation(self, client):
        """Test that line totals and the overall total add up."""
        data = get_recommendations(client, 25000)
        for item in data["items"]:
            assert abs(item["line_total"] - item["recommended_quantity"] * item["unit_cost"]) < 0.01
        assert abs(sum(i["line_total"] for i in data["items"]) - data["total_cost"]) < 0.01

    def test_recommendations_zero_budget(self, client):
        """Test that a zero budget recommends nothing."""
        data = get_recommendations(client, 0)
        assert data["total_cost"] == 0
        assert all(item["recommended_quantity"] == 0 for item in data["items"])

    def test_recommendations_large_budget_funds_all_needs(self, client):
        """Test that a budget above the total need funds every item fully."""
        data = get_recommendations(client, 10_000_000)
        assert all(i["recommended_quantity"] == i["needed_quantity"] for i in data["items"])
        assert abs(data["total_cost"] - data["total_needed_cost"]) < 0.01

    def test_recommendations_priority_order(self, client):
        """Test that items are ranked increasing, then stable, then decreasing trend."""
        items = get_recommendations(client, 25000)["items"]
        assert [i["priority"] for i in items] == list(range(1, len(items) + 1))
        ranks = [TREND_RANK[i["trend"].lower()] for i in items]
        assert ranks == sorted(ranks)

    def test_recommendations_greedy_fill(self, client):
        """Test that only the last funded item can be partial and nothing after it is funded."""
        items = get_recommendations(client, 25000)["items"]
        partial_seen = False
        for item in items:
            if partial_seen:
                assert item["recommended_quantity"] == 0
            elif item["recommended_quantity"] < item["needed_quantity"]:
                partial_seen = True
        assert partial_seen

    def test_recommendations_exclude_items_covered_by_stock(self, client):
        """Test that PSU-501 is excluded because inventory on hand covers its forecast."""
        skus = [i["sku"] for i in get_recommendations(client, 25000)["items"]]
        assert "PSU-501" not in skus

    def test_recommendations_lead_time_by_category(self, client):
        """Test that lead times come from the per-category table."""
        for item in get_recommendations(client, 25000)["items"]:
            expected = main.LEAD_TIME_DAYS.get(item["category"], main.DEFAULT_LEAD_TIME_DAYS)
            assert item["lead_time_days"] == expected

    def test_recommendations_negative_budget(self, client):
        """Test that a negative budget is rejected."""
        response = client.get("/api/restock-recommendations?budget=-1")
        assert response.status_code == 422

    def test_recommendations_missing_budget(self, client):
        """Test that the budget parameter is required."""
        response = client.get("/api/restock-recommendations")
        assert response.status_code == 422

    def test_demand_forecasts_include_pricing(self, client):
        """Test that demand forecasts now carry unit_cost and category."""
        for forecast in client.get("/api/demand").json():
            assert isinstance(forecast["unit_cost"], (int, float))
            assert forecast["unit_cost"] > 0
            assert isinstance(forecast["category"], str)


class TestRestockOrders:
    """Test suite for submitting and listing restock orders."""

    def place_recommended_order(self, client, budget=25000):
        recs = get_recommendations(client, budget)
        lines = [{"sku": i["sku"], "quantity": i["recommended_quantity"]}
                 for i in recs["items"] if i["recommended_quantity"] > 0]
        return client.post("/api/restock-orders", json={"budget": budget, "items": lines}), recs

    def test_get_all_restock_orders_empty(self, client):
        """Test that the list starts empty."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order(self, client):
        """Test submitting the recommended order."""
        response, recs = self.place_recommended_order(client)
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert abs(order["total_value"] - recs["total_cost"]) < 0.01
        assert len(order["items"]) > 0

    def test_restock_order_lead_time_calculation(self, client):
        """Test that order lead time is the longest item lead time and drives expected delivery."""
        order = self.place_recommended_order(client)[0].json()
        assert order["lead_time_days"] == max(i["lead_time_days"] for i in order["items"])

        created = datetime.fromisoformat(order["created_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert expected - created == timedelta(days=order["lead_time_days"])

    def test_restock_orders_listed_newest_first(self, client):
        """Test that submitted orders are listed, newest first."""
        first = client.post("/api/restock-orders",
                            json={"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 10}]}).json()
        second = client.post("/api/restock-orders",
                             json={"budget": 1000, "items": [{"sku": "GSK-203", "quantity": 10}]}).json()

        orders = client.get("/api/restock-orders").json()
        assert [o["id"] for o in orders] == [second["id"], first["id"]]

    def test_restock_order_reduces_future_need(self, client):
        """Test that quantities on order are subtracted from later recommendations."""
        before = {i["sku"]: i for i in get_recommendations(client, 0)["items"]}
        client.post("/api/restock-orders",
                    json={"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 10}]})
        after = {i["sku"]: i for i in get_recommendations(client, 0)["items"]}

        assert after["WDG-001"]["on_order"] == 10
        assert after["WDG-001"]["needed_quantity"] == before["WDG-001"]["needed_quantity"] - 10

    def test_restock_order_prices_from_server(self, client):
        """Test that line totals use server-side unit costs."""
        order = client.post("/api/restock-orders",
                            json={"budget": 1000, "items": [{"sku": "GSK-203", "quantity": 4}]}).json()
        assert order["items"][0]["unit_cost"] == 12.75
        assert abs(order["total_value"] - 51.0) < 0.01

    def test_restock_order_over_budget(self, client):
        """Test that an order above the budget is rejected."""
        response = client.post("/api/restock-orders",
                               json={"budget": 100, "items": [{"sku": "MTR-304", "quantity": 1}]})
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

    def test_restock_order_unknown_sku(self, client):
        """Test that an unknown SKU is rejected."""
        response = client.post("/api/restock-orders",
                               json={"budget": 1000, "items": [{"sku": "NOPE-999", "quantity": 1}]})
        assert response.status_code == 400

    def test_restock_order_quantity_exceeds_need(self, client):
        """Test that ordering more than the remaining need is rejected."""
        response = client.post("/api/restock-orders",
                               json={"budget": 1_000_000, "items": [{"sku": "WDG-001", "quantity": 100000}]})
        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"].lower()

    def test_restock_order_duplicate_sku(self, client):
        """Test that the same SKU twice in one order is rejected."""
        response = client.post("/api/restock-orders", json={
            "budget": 1000,
            "items": [{"sku": "WDG-001", "quantity": 1}, {"sku": "WDG-001", "quantity": 1}],
        })
        assert response.status_code == 400

    @pytest.mark.parametrize("payload", [
        {"budget": 1000, "items": []},
        {"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 0}]},
        {"budget": 0, "items": [{"sku": "WDG-001", "quantity": 1}]},
    ])
    def test_restock_order_invalid_payload(self, client, payload):
        """Test that empty items, zero quantity and zero budget fail validation."""
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 422
