"""
Test cases for chart validators and fixers.

Run tests：
    python -m pytest ReportEngine/utils/test_chart_validator.py -v
"""

import pytest
from ReportEngine.utils.chart_validator import (
    ChartValidator,
    ChartRepairer,
    ValidationResult,
    RepairResult,
    create_chart_validator,
    create_chart_repairer
)


class TestChartValidator:
    """Test the ChartValidator class"""

    def setup_method(self):
        """Initialize before each test"""
        self.validator = create_chart_validator()

    def test_valid_bar_chart(self):
        """Test a valid histogram"""
        widget_block = {
            "type": "widget",
            "widgetType": "chart.js/bar",
            "widgetId": "chart-001",
            "props": {
                "type": "bar",
                "title": "sales data"
            },
            "data": {
                "labels": ["January", "February", "March"],
                "datasets": [
                    {
                        "label": "sales",
                        "data": [100, 200, 150]
                    }
                ]
            }
        }

        result = self.validator.validate(widget_block)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_valid_line_chart(self):
        """Test a valid line chart"""
        widget_block = {
            "type": "widget",
            "widgetType": "chart.js/line",
            "widgetId": "chart-002",
            "props": {
                "type": "line"
            },
            "data": {
                "labels": ["on Monday", "Tuesday", "Wednesday"],
                "datasets": [
                    {
                        "label": "Visits",
                        "data": [50, 75, 60]
                    }
                ]
            }
        }

        result = self.validator.validate(widget_block)
        assert result.is_valid

    def test_valid_pie_chart(self):
        """Testing a valid pie chart"""
        widget_block = {
            "widgetType": "chart.js/pie",
            "props": {"type": "pie"},
            "data": {
                "labels": ["A", "B", "C"],
                "datasets": [
                    {
                        "data": [30, 40, 30]
                    }
                ]
            }
        }

        result = self.validator.validate(widget_block)
        assert result.is_valid

    def test_missing_widgetType(self):
        """test missingwidgetType"""
        widget_block = {
            "props": {},
            "data": {}
        }

        result = self.validator.validate(widget_block)
        assert not result.is_valid
        assert "widgetType" in result.errors[0]

    def test_missing_data_field(self):
        """Test is missing data field"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"}
        }

        result = self.validator.validate(widget_block)
        assert not result.is_valid
        assert "data" in result.errors[0]

    def test_missing_datasets(self):
        """test missingdatasets"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"]
            }
        }

        result = self.validator.validate(widget_block)
        assert not result.is_valid
        assert "datasets" in result.errors[0]

    def test_empty_datasets(self):
        """test emptydatasets"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"],
                "datasets": []
            }
        }

        result = self.validator.validate(widget_block)
        assert not result.is_valid
        assert "datasetsArray is empty" in result.errors[0]

    def test_missing_labels_for_bar_chart(self):
        """Test histogram is missinglabels"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "datasets": [
                    {
                        "label": "series1",
                        "data": [10, 20, 30]
                    }
                ]
            }
        }

        result = self.validator.validate(widget_block)
        assert not result.is_valid
        assert "labels" in result.errors[0]

    def test_invalid_data_type(self):
        """Wrong test data type"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"],
                "datasets": [
                    {
                        "label": "series1",
                        "data": ["abc", "def"]
                    }
                ]
            }
        }

        result = self.validator.validate(widget_block)
        assert not result.is_valid
        assert "Not a valid numeric type" in result.errors[0]

    def test_data_length_mismatch_warning(self):
        """Test data length mismatch (warning）"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B", "C"],
                "datasets": [
                    {
                        "label": "series1",
                        "data": [10, 20]
                    }
                ]
            }
        }

        result = self.validator.validate(widget_block)

        assert len(result.warnings) > 0
        assert "does not match" in result.warnings[0]

    def test_scatter_chart(self):
        """Test scatter plot (special data format）"""
        widget_block = {
            "widgetType": "chart.js/scatter",
            "props": {"type": "scatter"},
            "data": {
                "datasets": [
                    {
                        "label": "data points",
                        "data": [
                            {"x": 10, "y": 20},
                            {"x": 15, "y": 25}
                        ]
                    }
                ]
            }
        }

        result = self.validator.validate(widget_block)
        assert result.is_valid

    def test_non_chart_widget(self):
        """Test non-chart type widgets (validation should be skipped）"""
        widget_block = {
            "widgetType": "custom/widget",
            "props": {},
            "data": {}
        }

        result = self.validator.validate(widget_block)

        assert result.is_valid


class TestChartRepairer:
    """Test the ChartRepairer class"""

    def setup_method(self):
        """Initialize before each test"""
        self.validator = create_chart_validator()
        self.repairer = create_chart_repairer(validator=self.validator)

    def test_repair_missing_props(self):
        """Test fix missing props field"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "data": {
                "labels": ["A", "B"],
                "datasets": [
                    {
                        "label": "series1",
                        "data": [10, 20]
                    }
                ]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success
        assert "props" in result.repaired_block
        assert result.method == "local"

    def test_repair_missing_chart_type(self):
        """Test fix missing chart type"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {},
            "data": {
                "labels": ["A", "B"],
                "datasets": [
                    {
                        "label": "series1",
                        "data": [10, 20]
                    }
                ]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success
        assert result.repaired_block["props"]["type"] == "bar"
        assert "chart type" in str(result.changes)

    def test_repair_missing_datasets(self):
        """test fix missingdatasets"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success
        assert "datasets" in result.repaired_block["data"]
        assert isinstance(result.repaired_block["data"]["datasets"], list)

    def test_repair_missing_labels(self):
        """test fix missinglabels"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "datasets": [
                    {
                        "label": "series1",
                        "data": [10, 20, 30]
                    }
                ]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success
        assert "labels" in result.repaired_block["data"]
        assert len(result.repaired_block["data"]["labels"]) == 3

    def test_repair_data_length_mismatch(self):
        """Test to fix data length mismatch"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B", "C", "D"],
                "datasets": [
                    {
                        "label": "series1",
                        "data": [10, 20]
                    }
                ]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success

        assert len(result.repaired_block["data"]["datasets"][0]["data"]) == 4

    def test_repair_string_to_number(self):
        """Test to fix numeric values ​​of string type"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"],
                "datasets": [
                    {
                        "label": "series1",
                        "data": ["10", "20"]
                    }
                ]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success

        assert isinstance(result.repaired_block["data"]["datasets"][0]["data"][0], float)

    def test_repair_construct_datasets_from_values(self):
        """Tests are constructed from the values ​​fielddatasets"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"],
                "values": [10, 20]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success
        assert "datasets" in result.repaired_block["data"]
        assert len(result.repaired_block["data"]["datasets"]) > 0

    def test_no_repair_needed(self):
        """Test situations that don’t require fixing"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"],
                "datasets": [
                    {
                        "label": "series1",
                        "data": [10, 20]
                    }
                ]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success
        assert result.method == "none"
        assert len(result.changes) == 0

    def test_repair_adds_default_label(self):
        """test fix add defaultlabel"""
        widget_block = {
            "widgetType": "chart.js/bar",
            "props": {"type": "bar"},
            "data": {
                "labels": ["A", "B"],
                "datasets": [
                    {

                        "data": [10, 20]
                    }
                ]
            }
        }

        result = self.repairer.repair(widget_block)
        assert result.success
        assert "label" in result.repaired_block["data"]["datasets"][0]


class TestValidatorIntegration:
    """Integration testing"""

    def test_full_validation_and_repair_workflow(self):
        """Test the complete verification and remediation process"""
        validator = create_chart_validator()
        repairer = create_chart_repairer(validator=validator)


        widget_block = {
            "widgetType": "chart.js/bar",
            "data": {
                "datasets": [
                    {
                        "data": ["10", "20", "30"]
                    }
                ]
            }
        }


        validation = validator.validate(widget_block)
        assert not validation.is_valid


        repair_result = repairer.repair(widget_block, validation)
        assert repair_result.success


        final_validation = validator.validate(repair_result.repaired_block)
        assert final_validation.is_valid


if __name__ == "__main__":

    pytest.main([__file__, "-v", "--tb=short"])
