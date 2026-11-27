"""
Chart validation and repair tools.

Provide forChart.jsChart data verification and repair capabilities：
1. Verify whether the chart data format complies withChart.jsRequire
2. Local rules fixes FAQ
3. LLM APIAssist in repairing complex issues
4. follow"I would rather not change than correct my mistakes."principles

Supported chart types：
- line (Line chart)
- bar (bar chart)
- pie (pie chart)
- doughnut (donut chart)
- radar (radar chart)
- polararea (polar regions map)
- scatter (Scatter plot)
- bubble (bubble chart)
- horizontalbar (horizontal bar chart)
"""

from __future__ import annotations

import copy
import json
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from loguru import logger


@dataclass
class ValidationResult:
    """Verification results"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]

    def has_critical_errors(self) -> bool:
        """Is there a serious error (which will cause the rendering to fail?）"""
        return not self.is_valid and len(self.errors) > 0


@dataclass
class RepairResult:
    """Repair results"""
    success: bool
    repaired_block: Optional[Dict[str, Any]]
    method: str  # 'none', 'local', 'api'
    changes: List[str]

    def has_changes(self) -> bool:
        """Is there any modification?"""
        return len(self.changes) > 0


class ChartValidator:
    """
    Chart Validator - verifyChart.jsIs the chart data format correct?

    Validation rules：
    1. Basic structure verification：widgetType, props, dataField
    2. Chart type validation: supported chart types
    3. Data format verification: labels and datasets structure
    4. Data consistency verification: labels and datasets length match
    5. Numeric type verification: the data value type is correct
    """


    SUPPORTED_CHART_TYPES = {
        'line', 'bar', 'pie', 'doughnut', 'radar', 'polararea', 'scatter',
        'bubble', 'horizontalbar'
    }


    LABEL_REQUIRED_TYPES = {
        'line', 'bar', 'radar', 'polararea', 'pie', 'doughnut'
    }


    NUMERIC_DATA_TYPES = {
        'line', 'bar', 'radar', 'polararea', 'pie', 'doughnut'
    }


    SPECIAL_DATA_TYPES = {
        'scatter': {'x', 'y'},
        'bubble': {'x', 'y', 'r'}
    }

    def __init__(self):
        """Initialize the validator and reserve the cache structure to facilitate subsequent reuse and verification./Repair results"""

    def validate(self, widget_block: Dict[str, Any]) -> ValidationResult:
        """
        Validate chart format。

        Args:
            widget_block: widgettype of block, includingwidgetId/widgetType/props/data

        Returns:
            ValidationResult: Verification results
        """
        errors = []
        warnings = []


        if not isinstance(widget_block, dict):
            errors.append("widget_blockMust be of dictionary type")
            return ValidationResult(False, errors, warnings)


        widget_type = widget_block.get('widgetType', '')
        if not widget_type or not isinstance(widget_type, str):
            errors.append("The widgetType field is missing or incorrect type")
            return ValidationResult(False, errors, warnings)


        if not widget_type.startswith('chart.js'):

            return ValidationResult(True, errors, warnings)


        chart_type = self._extract_chart_type(widget_block)
        if not chart_type:
            errors.append("Unable to determine chart type")
            return ValidationResult(False, errors, warnings)


        if chart_type not in self.SUPPORTED_CHART_TYPES:
            warnings.append(f"chart type '{chart_type}' May not be supported, will try to downgrade rendering")


        data = widget_block.get('data')
        if not isinstance(data, dict):
            errors.append("dataField must be of dictionary type")
            return ValidationResult(False, errors, warnings)


        def contains_object_points(ds_list: List[Any] | None) -> bool:
            """Check if the data set containsx/yThe object point represented by the key, used to switch the verification branch"""
            if not isinstance(ds_list, list):
                return False
            for point in ds_list:
                if isinstance(point, dict) and any(key in point for key in ('x', 'y', 't')):
                    return True
            return False

        datasets_for_detection = data.get('datasets') or []
        uses_object_points = any(
            isinstance(ds, dict) and contains_object_points(ds.get('data'))
            for ds in datasets_for_detection
        )


        if chart_type in self.SPECIAL_DATA_TYPES:

            self._validate_special_data(data, chart_type, errors, warnings)
        else:

            self._validate_standard_data(data, chart_type, errors, warnings, uses_object_points)


        props = widget_block.get('props')
        if props is not None and not isinstance(props, dict):
            warnings.append("propsField should be of dictionary type")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings)

    def _extract_chart_type(self, widget_block: Dict[str, Any]) -> Optional[str]:
        """
        Extract chart type.

        priority：
        1. props.type
        2. widgetTypeTypes in（chart.js/bar -> bar）
        3. data.type
        """

        props = widget_block.get('props') or {}
        if isinstance(props, dict):
            chart_type = props.get('type')
            if chart_type and isinstance(chart_type, str):
                return chart_type.lower()


        widget_type = widget_block.get('widgetType', '')
        if '/' in widget_type:
            chart_type = widget_type.split('/')[-1]
            if chart_type:
                return chart_type.lower()


        data = widget_block.get('data') or {}
        if isinstance(data, dict):
            chart_type = data.get('type')
            if chart_type and isinstance(chart_type, str):
                return chart_type.lower()

        return None

    def _validate_standard_data(
        self,
        data: Dict[str, Any],
        chart_type: str,
        errors: List[str],
        warnings: List[str],
        uses_object_points: bool = False
    ):
        """Verify standard data format（labels + datasets）"""
        labels = data.get('labels')
        datasets = data.get('datasets')


        if chart_type in self.LABEL_REQUIRED_TYPES:
            if not labels:
                if uses_object_points:
                    warnings.append(
                        f"{chart_type}Type chart is missing labels and has been rendered based on data points (using x values）"
                    )
                else:
                    errors.append(f"{chart_type}Type chart must contain labels field")
            elif not isinstance(labels, list):
                errors.append("labelsMust be an array type")
            elif len(labels) == 0:
                warnings.append("labelsThe array is empty and the chart may not display properly.")


        if datasets is None:
            errors.append("Missing datasets field")
            return

        if not isinstance(datasets, list):
            errors.append("datasetsMust be an array type")
            return

        if len(datasets) == 0:
            errors.append("datasetsArray is empty")
            return


        for idx, dataset in enumerate(datasets):
            if not isinstance(dataset, dict):
                errors.append(f"datasets[{idx}]Must be of object type")
                continue


            ds_data = dataset.get('data')
            if ds_data is None:
                errors.append(f"datasets[{idx}]missing data field")
                continue

            if not isinstance(ds_data, list):
                errors.append(f"datasets[{idx}].dataMust be an array type")
                continue

            if len(ds_data) == 0:
                warnings.append(f"datasets[{idx}].dataArray is empty")
                continue


            object_points = any(
                isinstance(value, dict) and any(key in value for key in ('x', 'y', 't'))
                for value in ds_data
            )


            if labels and isinstance(labels, list) and not object_points:
                if len(ds_data) != len(labels):
                    warnings.append(
                        f"datasets[{idx}].datalength({len(ds_data)})and length of labels({len(labels)})does not match"
                    )


            if chart_type in self.NUMERIC_DATA_TYPES and not object_points:
                for data_idx, value in enumerate(ds_data):
                    if value is not None and not isinstance(value, (int, float)):
                        errors.append(
                            f"datasets[{idx}].data[{data_idx}]value'{value}'Not a valid numeric type"
                        )
                        break

    def _validate_special_data(
        self,
        data: Dict[str, Any],
        chart_type: str,
        errors: List[str],
        warnings: List[str]
    ):
        """Validate special data formats（scatter, bubble）"""
        datasets = data.get('datasets')

        if not datasets:
            errors.append("Missing datasets field")
            return

        if not isinstance(datasets, list):
            errors.append("datasetsMust be an array type")
            return

        if len(datasets) == 0:
            errors.append("datasetsArray is empty")
            return

        required_keys = self.SPECIAL_DATA_TYPES.get(chart_type, set())


        for idx, dataset in enumerate(datasets):
            if not isinstance(dataset, dict):
                errors.append(f"datasets[{idx}]Must be of object type")
                continue

            ds_data = dataset.get('data')
            if ds_data is None:
                errors.append(f"datasets[{idx}]missing data field")
                continue

            if not isinstance(ds_data, list):
                errors.append(f"datasets[{idx}].dataMust be an array type")
                continue

            if len(ds_data) == 0:
                warnings.append(f"datasets[{idx}].dataArray is empty")
                continue


            for data_idx, point in enumerate(ds_data):
                if not isinstance(point, dict):
                    errors.append(
                        f"datasets[{idx}].data[{data_idx}]Must be an object type (including{required_keys}Field）"
                    )
                    break


                missing_keys = required_keys - set(point.keys())
                if missing_keys:
                    errors.append(
                        f"datasets[{idx}].data[{data_idx}]Missing required field: {missing_keys}"
                    )
                    break


                for key in required_keys:
                    value = point.get(key)
                    if value is not None and not isinstance(value, (int, float)):
                        errors.append(
                            f"datasets[{idx}].data[{data_idx}].{key}value'{value}'Not a valid numeric type"
                        )
                        break

    def can_render(self, widget_block: Dict[str, Any]) -> bool:
        """
        Determine whether the chart can render normally (quick check）。

        Args:
            widget_block: widgettypeblock

        Returns:
            bool: Whether it can be rendered normally
        """
        result = self.validate(widget_block)
        return result.is_valid


class ChartRepairer:
    """
    chart fixer - Try to fix the chart data.

    Repair strategy：
    1. Local rules fixes: fixes for common issues
    2. APIRepair: Fix complex problems using LLM
    3. Verify the repair results: Make sure it can render normally after repair
    """

    def __init__(
        self,
        validator: ChartValidator,
        llm_repair_fns: Optional[List[Callable]] = None
    ):
        """
        Initialize fixer。

        Args:
            validator: Chart Validator Example
            llm_repair_fns: LLMRepair function list (corresponding to 4Engine）
        """
        self.validator = validator
        self.llm_repair_fns = llm_repair_fns or []

        self._result_cache: Dict[str, RepairResult] = {}

    def build_cache_key(self, widget_block: Dict[str, Any]) -> str:
        """
        Generate stable cache keys for charts to ensure that the same data will not trigger repairs repeatedly。

        - priority usewidgetId；
        - Combined with the hash of data content to avoid misuse of old results when the content of the same ID changes.。
        """
        widget_id = ""
        if isinstance(widget_block, dict):
            widget_id = widget_block.get('widgetId') or widget_block.get('id') or ""
        try:
            serialized = json.dumps(
                widget_block,
                ensure_ascii=False,
                sort_keys=True,
                default=str
            )
        except Exception:
            serialized = repr(widget_block)
        digest = hashlib.md5(serialized.encode('utf-8', errors='ignore')).hexdigest()
        return f"{widget_id}:{digest}"

    def repair(
        self,
        widget_block: Dict[str, Any],
        validation_result: Optional[ValidationResult] = None
    ) -> RepairResult:
        """
        Try to repair chart data。

        Args:
            widget_block: widgettypeblock
            validation_result: Verification results (optional, if not, verification will be performed first）

        Returns:
            RepairResult: Repair results
        """
        cache_key = self.build_cache_key(widget_block)

        cached = self._result_cache.get(cache_key)
        if cached:

            return copy.deepcopy(cached)

        def _cache_and_return(res: RepairResult) -> RepairResult:
            """Write the repair result cache and return it to avoid repeated calls to downstream repair logic"""
            try:
                self._result_cache[cache_key] = copy.deepcopy(res)
            except Exception:
                self._result_cache[cache_key] = res
            return res


        if validation_result is None:
            validation_result = self.validator.validate(widget_block)


        current_validation = validation_result
        current_block = widget_block


        logger.info(f"Try to fix the chart locally")
        local_result = self.repair_locally(widget_block, validation_result)


        if local_result.has_changes():
            repaired_validation = self.validator.validate(local_result.repaired_block)
            if repaired_validation.is_valid:
                logger.info(f"Local repair successful: {local_result.changes}")
                return _cache_and_return(
                    RepairResult(True, local_result.repaired_block, 'local', local_result.changes)
                )
            else:
                logger.warning(f"Still ineffective after local repair: {repaired_validation.errors}")

                current_validation = repaired_validation
                current_block = local_result.repaired_block



        if current_validation.has_critical_errors() and len(self.llm_repair_fns) > 0:
            logger.info("Local repair fails or is insufficient, try API repair")

            api_result = self.repair_with_api(current_block, current_validation)

            if api_result.success:

                api_repaired_validation = self.validator.validate(api_result.repaired_block)
                if api_repaired_validation.is_valid:
                    logger.info(f"APIRepair successful: {api_result.changes}")
                    return _cache_and_return(api_result)
                else:
                    logger.warning(f"APIStill doesn’t work after repair: {api_repaired_validation.errors}")


        if validation_result.is_valid:
            if local_result.has_changes():
                return _cache_and_return(
                    RepairResult(True, local_result.repaired_block, 'local', local_result.changes)
                )
            else:
                return _cache_and_return(RepairResult(True, widget_block, 'none', []))


        logger.warning("All repair attempts fail, original data retained")

        final_block = local_result.repaired_block if local_result.has_changes() else widget_block
        return _cache_and_return(RepairResult(False, final_block, 'none', []))

    def repair_locally(
        self,
        widget_block: Dict[str, Any],
        validation_result: ValidationResult
    ) -> RepairResult:
        """
        Fix using local rules.

        Repair rules：
        1. Complete missing basic fields
        2. Fix data type errors
        3. Fix data length mismatch
        4. Clean invalid data
        5. Add default value
        """
        repaired = copy.deepcopy(widget_block)
        changes = []


        if 'props' not in repaired or not isinstance(repaired.get('props'), dict):
            repaired['props'] = {}
            changes.append("Add missing props field")

        if 'data' not in repaired or not isinstance(repaired.get('data'), dict):
            repaired['data'] = {}
            changes.append("Add missing data fields")


        chart_type = self.validator._extract_chart_type(repaired)
        props = repaired['props']

        if not chart_type:

            widget_type = repaired.get('widgetType', '')
            if '/' in widget_type:
                chart_type = widget_type.split('/')[-1].lower()
                props['type'] = chart_type
                changes.append(f"Infer chart type from widgetType: {chart_type}")
            else:

                chart_type = 'bar'
                props['type'] = chart_type
                changes.append("Set default chart type: bar")
        elif 'type' not in props or not props['type']:

            props['type'] = chart_type
            changes.append(f"Add inferred chart type toprops: {chart_type}")


        data = repaired['data']


        if 'datasets' not in data or not isinstance(data.get('datasets'), list):
            data['datasets'] = []
            changes.append("Add missing datasets field")


        if len(data['datasets']) == 0:
            constructed = self._try_construct_datasets(data, chart_type)
            if constructed:
                data['datasets'] = constructed
                changes.append("constructed from datadatasets")
            elif 'labels' in data and isinstance(data.get('labels'), list) and len(data['labels']) > 0:

                data['datasets'] = [{
                    'label': 'data',
                    'data': [0] * len(data['labels'])
                }]
                changes.append("Create a default dataset based on labels (use zero value）")


        if chart_type in ChartValidator.LABEL_REQUIRED_TYPES:
            if 'labels' not in data or not isinstance(data.get('labels'), list):

                if data['datasets'] and len(data['datasets']) > 0:
                    first_ds = data['datasets'][0]
                    if isinstance(first_ds, dict) and isinstance(first_ds.get('data'), list):
                        data_len = len(first_ds['data'])
                        data['labels'] = [f"project {i+1}" for i in range(data_len)]
                        changes.append(f"generate{data_len}defaultlabels")


        for idx, dataset in enumerate(data.get('datasets', [])):
            if not isinstance(dataset, dict):
                continue


            if 'data' not in dataset or not isinstance(dataset.get('data'), list):
                dataset['data'] = []
                changes.append(f"fordatasets[{idx}]Add empty data array")


            if 'label' not in dataset:
                dataset['label'] = f"series {idx + 1}"
                changes.append(f"fordatasets[{idx}]add defaultlabel")


            labels = data.get('labels', [])
            ds_data = dataset.get('data', [])
            if isinstance(labels, list) and isinstance(ds_data, list):
                if len(ds_data) < len(labels):

                    dataset['data'] = ds_data + [None] * (len(labels) - len(ds_data))
                    changes.append(f"datasets[{idx}]Insufficient data length, please addnull")
                elif len(ds_data) > len(labels):

                    dataset['data'] = ds_data[:len(labels)]
                    changes.append(f"datasets[{idx}]Data length is too long, truncated")


            if chart_type in ChartValidator.NUMERIC_DATA_TYPES:
                ds_data = dataset.get('data', [])
                converted = False
                for i, value in enumerate(ds_data):
                    if value is None:
                        continue
                    if not isinstance(value, (int, float)):

                        try:
                            if isinstance(value, str):

                                ds_data[i] = float(value)
                                converted = True
                        except (ValueError, TypeError):

                            ds_data[i] = None
                            converted = True
                if converted:
                    changes.append(f"datasets[{idx}]Contains non-numeric data, conversion attempted")


        success = len(changes) > 0

        return RepairResult(success, repaired, 'local', changes)

    def _try_construct_datasets(
        self,
        data: Dict[str, Any],
        chart_type: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Try to construct from datadatasets"""

        if 'values' in data and isinstance(data['values'], list):
            return [{
                'label': 'data',
                'data': data['values']
            }]


        if 'series' in data and isinstance(data['series'], list):
            datasets = []
            for idx, series in enumerate(data['series']):
                if isinstance(series, dict):
                    datasets.append({
                        'label': series.get('name', f'series {idx + 1}'),
                        'data': series.get('data', [])
                    })
                elif isinstance(series, list):
                    datasets.append({
                        'label': f'series {idx + 1}',
                        'data': series
                    })
            if datasets:
                return datasets

        return None

    def repair_with_api(
        self,
        widget_block: Dict[str, Any],
        validation_result: ValidationResult
    ) -> RepairResult:
        """
        Fix using API (call LLM of 4 Engines).

        Strategy: Try different Engines in sequence until the repair is successful
        """
        if not self.llm_repair_fns:
            logger.debug("No LLM repair function available, API repair skipped")
            return RepairResult(False, None, 'api', [])

        widget_id = widget_block.get('widgetId', 'unknown')
        logger.info(f"chart {widget_id} Start API fix, total {len(self.llm_repair_fns)} Engines available")

        for idx, repair_fn in enumerate(self.llm_repair_fns):
            try:
                logger.info(f"Try usingEngine {idx + 1}/{len(self.llm_repair_fns)} Repair chart {widget_id}")
                repaired = repair_fn(widget_block, validation_result.errors)

                if repaired and isinstance(repaired, dict):

                    repaired_validation = self.validator.validate(repaired)
                    if repaired_validation.is_valid:
                        logger.info(f"chart {widget_id} useEngine {idx + 1} Repair successful")
                        return RepairResult(
                            True,
                            repaired,
                            'api',
                            [f"useEngine {idx + 1}Repair successful"]
                        )
                    else:
                        logger.warning(
                            f"chart {widget_id} Engine {idx + 1} Validation of returned data failed: "
                            f"{repaired_validation.errors}"
                        )
                else:
                    logger.warning(f"chart {widget_id} Engine {idx + 1} Returns an empty or invalid response")
            except Exception as e:

                logger.exception(f"chart {widget_id} Engine {idx + 1} An exception occurred during the repair process: {e}")
                continue

        logger.warning(f"chart {widget_id} all {len(self.llm_repair_fns)} All engines failed to be repaired")
        return RepairResult(False, None, 'api', [])


def create_chart_validator() -> ChartValidator:
    """Create a chart validator instance"""
    return ChartValidator()


def create_chart_repairer(
    validator: Optional[ChartValidator] = None,
    llm_repair_fns: Optional[List[Callable]] = None
) -> ChartRepairer:
    """Create a chart fixer instance"""
    if validator is None:
        validator = create_chart_validator()
    return ChartRepairer(validator, llm_repair_fns)
