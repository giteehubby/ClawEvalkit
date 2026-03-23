#!/usr/bin/env python3
"""
Universal benchmark evaluation script for results JSON files.
Works directly with results.json files without needing original benchmark files.
"""

import re
import json
import ast
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime
from collections import Counter
import os

class UniversalBenchmarkEvaluator:
    """
    Universal evaluator for results JSON files.
    Works directly with results data without needing original benchmark files.
    """
    
    def __init__(self, results_json_path: str):
        self.results_json_path = results_json_path
        # Only load results data if the file exists (for testing purposes)
        if os.path.exists(results_json_path):
            self.results_data = self._load_results_data()
        else:
            self.results_data = []

    def fix_processed_output(self, s):
        """
        Attempt to automatically fix common bracket and comma issues in processed_output strings.
        - Removes extra closing brackets or braces at the end.
        - Balances the number of '[' and ']'.
        - Removes trailing commas before closing brackets/braces.
        Only applies to string inputs that are not 'Failed'.
        """
        if not isinstance(s, str) or s.strip() == "Failed":
            return s
        # Remove extra closing braces or parentheses at the end
        s = re.sub(r'[\}\)]+$', '', s)
        # Balance square brackets
        n_left = s.count('[')
        n_right = s.count(']')
        if n_left > n_right:
            s += ']' * (n_left - n_right)
        elif n_right > n_left:
            s = s.rstrip(']')
            s += ']' * n_left
        # Remove trailing commas before closing brackets/braces
        s = re.sub(r',([\s]*[\]\}])', r'\1', s)
        return s
    
    def _load_results_data(self) -> List[Dict]:
        """Load results data from JSON file."""
        with open(self.results_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _parse_result(self, result_text: str) -> Any:
        """
        Parse result text into appropriate Python data type.
        Supports nested structures like [float, [float, float, float]].
        Automatically attempts to fix common bracket/comma issues before parsing.
        """
        # Attempt to fix common bracket/comma issues
        result_text = self.fix_processed_output(result_text)
        try:
            # JSON parsing - handles most cases including nested structures
            return json.loads(result_text)
        except:
            pass
        try:
            # ast.literal_eval - safely evaluates Python literals
            return ast.literal_eval(result_text)
        except:
            pass
        try:
            # Number parsing for simple cases
            if '.' in result_text:
                return float(result_text)
            else:
                return int(result_text)
        except:
            pass
        # Return as string if all parsing fails, but only if not empty
        cleaned_text = result_text.strip()
        return cleaned_text if cleaned_text else None
    
    def _parse_tolerance(self, tolerance_str: Optional[str]) -> Union[float, int, list, str]:
        """Parse tolerance string to numeric value, list structure, or string."""
        try:
            if tolerance_str is None or tolerance_str == 'N/A':
                return 0.0
            
            # Check for special string tolerances first
            if tolerance_str in ["exact_match", "semantic_match", "exact_values_458_524"]:
                return tolerance_str
            
            # Try to parse as JSON first (for complex structures)
            try:
                import json
                return json.loads(tolerance_str)
            except:
                pass
            
            # Try to parse as Python literal (for lists, etc.)
            try:
                import ast
                return ast.literal_eval(tolerance_str)
            except:
                pass
            
            # Try simple numeric parsing
            if '.' in tolerance_str:
                return float(tolerance_str)
            else:
                return int(tolerance_str)
        except:
            return 0.0
    
    def compare_answers(self, actual: Any, expected: Any, tolerance: Union[float, int, list, str]) -> Tuple[bool, Dict]:
        """
        Universal answer comparison with detailed difference information.
        Returns (is_correct, difference_info)
        """
        if actual is None:
            return False, {"error": "Actual result is None"}
        
        try:
            is_correct, diff_info = self._compare_recursive_with_diff(actual, expected, tolerance)
            return is_correct, diff_info
        except Exception as e:
            return False, {"error": f"Comparison error: {str(e)}"}
    
    def _compare_recursive_with_diff(self, actual: Any, expected: Any, tolerance: Union[float, int, list, str]) -> Tuple[bool, Dict]:
        """
        Enhanced recursive comparison with detailed difference information.
        Returns (is_correct, difference_info)
        """
        
        # Special case: for string lists with 'exact match' tolerance, use order/whitespace-insensitive comparison
        if tolerance == "exact_match":
            if (
                isinstance(expected, list) and isinstance(actual, list)
                and all(isinstance(e, str) for e in expected)
                and all(isinstance(a, str) for a in actual)
            ):
                # Special handling for two-element MP ID pairs with optional '-r2SCAN' or '-GGA+U' suffixes
                def _is_mp_pair_with_optional_suffix(items: List[Any]) -> bool:
                    if not isinstance(items, list) or len(items) != 2:
                        return False
                    for s in items:
                        if not isinstance(s, str):
                            return False
                        if re.match(r'^(mp-\d+)(?:-(?:r2scan|gga\+u))?$', s.strip(), flags=re.IGNORECASE) is None:
                            return False
                    return True

                def _normalize_mpid_optional_suffix(s: str) -> str:
                    m = re.match(r'^(mp-\d+)(?:-(?:r2scan|gga\+u))?$', str(s).strip(), flags=re.IGNORECASE)
                    return m.group(1) if m else str(s).strip()

                if _is_mp_pair_with_optional_suffix(actual) and _is_mp_pair_with_optional_suffix(expected):
                    actual_norm = sorted(_normalize_mpid_optional_suffix(x) for x in actual)
                    expected_norm = sorted(_normalize_mpid_optional_suffix(x) for x in expected)
                    is_correct = actual_norm == expected_norm
                    return is_correct, {"type": "mp_id_pair_optional_suffix", "is_correct": is_correct}

                # Default behavior: order/whitespace-insensitive comparison for string lists
                is_correct = self._compare_string_lists_order_independent(actual, expected)
                return is_correct, {"type": "string_list_exact_match", "is_correct": is_correct}
            elif isinstance(expected, str) and isinstance(actual, str):
                # Special case: chemical formula format normalization
                # Handle cases like 'Na4 Ti1 O4' vs 'Na4TiO4' vs "Na4TiO4"
                def _normalize_chemical_formula(s: str) -> str:
                    # Remove all whitespace and quotes
                    normalized = s.replace(' ', '').replace('"', '').replace("'", '')
                    # Remove '1' after element symbols (e.g., Ti1 -> Ti, O1 -> O)
                    normalized = re.sub(r'([A-Za-z])1([A-Za-z]|$)', r'\1\2', normalized)
                    return normalized
                
                # Check if both strings look like chemical formulas (contain letters and numbers)
                def _is_chemical_formula(s: str) -> bool:
                    # More specific heuristic: must contain both letters and numbers, and follow chemical formula pattern
                    clean = s.replace(' ', '').replace('"', '').replace("'", '')
                    # Pattern: letters followed by numbers (like Na4TiO4, H2O, etc.)
                    has_numbers = any(c.isdigit() for c in clean)
                    has_letters = any(c.isalpha() for c in clean)
                    
                    # Only process formulas that contain both letters and numbers
                    if has_numbers and has_letters:
                        # Complex formulas with numbers: Na4TiO4, H2O, LiFeO3, etc.
                        return bool(re.match(r'^[A-Za-z]+[0-9]+[A-Za-z0-9]*$', clean))
                    else:
                        return False
                
                if _is_chemical_formula(expected) and _is_chemical_formula(actual):
                    expected_norm = _normalize_chemical_formula(expected)
                    actual_norm = _normalize_chemical_formula(actual)
                    is_correct = expected_norm == actual_norm
                    return is_correct, {"type": "chemical_formula_exact_match", "is_correct": is_correct}
                
                # Default behavior: Compare strings after removing all whitespace
                is_correct = actual.replace(' ', '') == expected.replace(' ', '')
                return is_correct, {"type": "string_exact_match", "is_correct": is_correct}
            else:
                is_correct = actual == expected
                return is_correct, {"type": "exact_match", "is_correct": is_correct}
        
                # Special case: for 'semantic_match' tolerance for robocrystallographer benchmark, use 70% string similarity for strings
        if tolerance == "semantic_match":
            if isinstance(expected, str) and isinstance(actual, str):
                # Calculate similarity based on common content
                similarity = self._calculate_string_similarity(actual, expected)
                is_correct = similarity >= 0.70  # 70% threshold
                return is_correct, {
                    "type": "semantic_match",
                    "is_correct": is_correct,
                    "similarity": similarity,
                    "threshold": 0.70
                }
            elif (
                isinstance(expected, list) and isinstance(actual, list)
                and all(isinstance(e, str) for e in expected)
                and all(isinstance(a, str) for a in actual)
            ):
                # For string lists, check if most elements match semantically
                is_correct = self._compare_string_lists_semantic(actual, expected)
                return is_correct, {"type": "string_list_semantic_match", "is_correct": is_correct}
            else:
                # For other types, fall back to exact match
                is_correct = actual == expected
                return is_correct, {"type": "semantic_match_fallback", "is_correct": is_correct}
        
        # Try to convert both to the same type for comparison
        # If both can be converted to numbers, compare as numbers
        if isinstance(expected, (int, float)) or isinstance(actual, (int, float)):
            return self._compare_numbers_with_diff(actual, expected, tolerance)
        elif isinstance(expected, str) or isinstance(actual, str):
            is_correct = self._compare_strings(actual, expected)
            return is_correct, {"type": "string", "is_correct": is_correct}
        elif isinstance(expected, list) and isinstance(actual, list):
            return self._compare_lists_with_diff(actual, expected, tolerance)
        elif isinstance(expected, dict) and isinstance(actual, dict):
            return self._compare_dicts_with_diff(actual, expected, tolerance)
        else:
            is_correct = actual == expected
            return is_correct, {"type": "direct", "is_correct": is_correct}
    
    def _compare_string_lists_order_independent(self, actual: List[str], expected: List[str]) -> bool:
        """
        Compare string lists allowing order changes and ignoring whitespace.
        Example: ["A", "B"] matches ["B", "A"], and whitespace is ignored.
        """
        def _normalize_str(s):
            return str(s).replace(' ', '')
        if len(actual) != len(expected):
            return False
        # Use Counter to handle duplicates correctly, ignore whitespace
        actual_counter = Counter(_normalize_str(item) for item in actual)
        expected_counter = Counter(_normalize_str(item) for item in expected)
        return actual_counter == expected_counter
    
    def _compare_numbers_with_diff(self, actual: Union[int, float], expected: Union[int, float], 
                                  tolerance: Union[int, float, list]) -> Tuple[bool, Dict]:
        """
        Compare numeric values with tolerance and return detailed difference.
        """
        try:
            actual_num = float(actual)
            expected_num = float(expected)
            
            difference = abs(actual_num - expected_num)
            
            if tolerance == 0:
                is_correct = actual_num == expected_num
            elif tolerance == "exact_values_458_524":
                # Special case: only allow exact values 458 or 524
                is_correct = actual_num == 458 or actual_num == 524
            else:
                # Handle both numeric and list tolerances
                if isinstance(tolerance, (int, float)):
                    tolerance_val = abs(tolerance)
                else:
                    # For list tolerances, use the first element or default to 0
                    tolerance_val = tolerance[0] if isinstance(tolerance, list) and len(tolerance) > 0 else 0
                
                is_correct = difference <= tolerance_val
            
            if tolerance == "exact_values_458_524":
                diff_info = {
                    "type": "number_exact_values",
                    "actual": actual_num,
                    "expected_values": [458, 524],
                    "is_correct": is_correct
                }
            else:
                diff_info = {
                    "type": "number",
                    "actual": actual_num,
                    "expected": expected_num,
                    "difference": difference,
                    "tolerance": tolerance_val if tolerance != 0 else 0,
                    "is_correct": is_correct
                }
            
            return is_correct, diff_info
        except Exception as e:
            return False, {"type": "number", "error": f"Number comparison error: {str(e)}"}
    
    def _compare_strings(self, actual: Optional[str], expected: Optional[str]) -> bool:
        """Compare string values after stripping whitespace."""
        if actual is None or expected is None:
            return actual == expected
        return str(actual).strip() == str(expected).strip()
    
    def _compare_lists_with_diff(self, actual: List, expected: List, tolerance: Union[float, int, list]) -> Tuple[bool, Dict]:
        """
        Compare lists with detailed difference information.
        """
        # Special case: for string lists with 'exact match' tolerance, use order/whitespace-insensitive comparison
        if (
            tolerance == "exact match"
            and isinstance(expected, list) and isinstance(actual, list)
            and all(isinstance(e, str) for e in expected)
            and all(isinstance(a, str) for a in actual)
        ):
            is_correct = self._compare_string_lists_order_independent(actual, expected)
            return is_correct, {"type": "string_list_exact_match", "is_correct": is_correct}

        if len(actual) != len(expected):
            return False, {"type": "list", "error": f"Length mismatch: actual={len(actual)}, expected={len(expected)}"}

        # Ordered comparison for mixed types or numeric lists
        all_correct = True
        element_diffs = []
        
        for i, (a, e) in enumerate(zip(actual, expected)):
            # Determine tolerance for this element
            if isinstance(tolerance, list) and i < len(tolerance):
                element_tolerance = tolerance[i]
            else:
                element_tolerance = tolerance

            # Recursive comparison
            element_correct, element_diff = self._compare_recursive_with_diff(a, e, element_tolerance)
            
            element_diffs.append({
                "index": i,
                "actual": a,
                "expected": e,
                "tolerance": element_tolerance,
                "is_correct": element_correct,
                "difference_info": element_diff
            })
            
            if not element_correct:
                all_correct = False

        diff_info = {
            "type": "list",
            "length": len(actual),
            "is_correct": all_correct,
            "element_differences": element_diffs
        }
        
        return all_correct, diff_info
    
    def _compare_dicts_with_diff(self, actual: dict, expected: dict, tolerance: Union[float, int]) -> Tuple[bool, Dict]:
        """Compare dictionary values with detailed difference information."""
        if actual.keys() != expected.keys():
            return False, {"type": "dict", "error": f"Key mismatch: actual_keys={list(actual.keys())}, expected_keys={list(expected.keys())}"}
        
        all_correct = True
        key_diffs = []
        
        for key in expected.keys():
            key_correct, key_diff = self._compare_recursive_with_diff(actual[key], expected[key], tolerance)
            
            key_diffs.append({
                "key": key,
                "actual": actual[key],
                "expected": expected[key],
                "tolerance": tolerance,
                "is_correct": key_correct,
                "difference_info": key_diff
            })
            
            if not key_correct:
                all_correct = False
        
        diff_info = {
            "type": "dict",
            "keys": list(expected.keys()),
            "is_correct": all_correct,
            "key_differences": key_diffs
        }
        
        return all_correct, diff_info
    
    def _extract_category_from_filename(self, filename: str) -> str:
        """Extract category name from results filename."""
        # Remove 'results_' prefix and '.json' suffix
        category = filename.replace('results_', '').replace('.json', '')
        return category
    
    def _calculate_level_success_rate(self, results: List[Dict]) -> Dict[str, Dict]:
        """
        Calculate success rate, completion rate, and execution time for each level (0 and 1) separately.
        """
        level_stats = {'0': {'correct': 0, 'total': 0, 'total_attempts': 0, 'execution_times': []}, 
                      '1': {'correct': 0, 'total': 0, 'total_attempts': 0, 'execution_times': []}}
        
        for result in results:
            level_id = result.get('level_id', 0)
            level_key = str(level_id)
            
            if level_key not in level_stats:
                level_stats[level_key] = {'correct': 0, 'total': 0, 'total_attempts': 0, 'execution_times': []}
            
            # Count total attempts (including workflow failed)
            level_stats[level_key]['total_attempts'] += 1
            
            # Check if answer is correct
            processed_output = result.get('processed_output', '')
            expected_answer = result.get('answer', 'N/A')
            tolerance_str = result.get('tolerance', '0')
            
            # Skip "Workflow Failed" attempts for success rate calculation
            if processed_output == "Workflow Failed":
                continue
            
            level_stats[level_key]['total'] += 1
            
            # Collect execution time if available
            execution_time = result.get('execution_time_seconds')
            if execution_time is not None:
                level_stats[level_key]['execution_times'].append(execution_time)
            
            if processed_output and processed_output.lower() != 'failed':
                try:
                    parsed_answer = self._parse_result(processed_output)
                    expected_parsed = self._parse_result(expected_answer)
                    tolerance = self._parse_tolerance(tolerance_str)
                    
                    is_correct, diff_info = self.compare_answers(parsed_answer, expected_parsed, tolerance)
                    if is_correct:
                        level_stats[level_key]['correct'] += 1
                except:
                    pass
        
        # Calculate all metrics for each level
        for level in level_stats:
            total = level_stats[level]['total']
            correct = level_stats[level]['correct']
            total_attempts = level_stats[level]['total_attempts']
            execution_times = level_stats[level]['execution_times']
            
            # Calculate metrics
            level_stats[level]['success_rate'] = (correct / total * 100) if total > 0 else 0.0
            level_stats[level]['completion_rate'] = (total / total_attempts * 100) if total_attempts > 0 else 0.0
            level_stats[level]['average_execution_time'] = (sum(execution_times) / len(execution_times)) if execution_times else 0.0
        
        return level_stats
    
    def _calculate_pass_at_n(self, results: List[Dict], calculate_per_level: bool = False) -> Dict[str, float]:
        """
        Calculate Pass@1, Pass@2, Pass@3 metrics.
        Pass@n = percentage of questions where at least one of the first n valid attempts is correct.
        Workflow failed attempts are excluded from counting.
        
        Args:
            results: List of result dictionaries
            calculate_per_level: If True, calculate Pass@n for each level separately
        """
        # Group results by question (using level_id + question as key)
        question_groups = {}
        for result in results:
            level_id = result.get('level_id', 0)
            question = result.get('question', '')
            key = (level_id, question)
            if key not in question_groups:
                question_groups[key] = []
            question_groups[key].append(result)
        
        # Sort attempts by timestamp to ensure correct order for Pass@n calculation
        for key in question_groups:
            question_groups[key].sort(key=lambda x: x.get('timestamp', ''))
        
        # Initialize counters
        if calculate_per_level:
            # Per-level counters (dynamically discovered from data)
            level_pass_at_1_count = {}
            level_pass_at_2_count = {}
            level_pass_at_3_count = {}
            level_total_questions = {}
            
            # Count questions per level first
            for (level_id, question), attempts in question_groups.items():
                level_key = str(level_id)
                if level_key not in level_total_questions:
                    level_total_questions[level_key] = 0
                    level_pass_at_1_count[level_key] = 0
                    level_pass_at_2_count[level_key] = 0
                    level_pass_at_3_count[level_key] = 0
                level_total_questions[level_key] += 1
        else:
            # Overall counters
            pass_at_1_count = 0
            pass_at_2_count = 0
            pass_at_3_count = 0
            total_questions = len(question_groups)
        
        for (level_id, question), attempts in question_groups.items():
            # Filter out workflow failed attempts and check correctness
            valid_attempts = []
            for attempt in attempts:
                processed_output = attempt.get('processed_output', '')
                
                # Skip workflow failed attempts
                if processed_output == "Workflow Failed":
                    continue
                
                # Check if this attempt is correct
                if processed_output and processed_output.lower() != 'failed':
                    try:
                        expected_answer_str = attempt.get('answer', 'N/A')
                        tolerance_str = attempt.get('tolerance', '0')
                        
                        parsed_answer = self._parse_result(processed_output)
                        expected_parsed = self._parse_result(expected_answer_str)
                        tolerance = self._parse_tolerance(tolerance_str)
                        
                        # Special case: if expected_answer is a string or list of strings and tolerance is 0, set to 'exact match'
                        # But don't override if tolerance is already set to 'semantic_match'
                        def is_str_or_list_of_str(x):
                            if isinstance(x, str):
                                return True
                            if isinstance(x, list) and all(isinstance(i, str) for i in x):
                                return True
                            return False
                        if is_str_or_list_of_str(expected_parsed) and (tolerance == 0 or tolerance == 0.0) and tolerance != "semantic_match":
                            tolerance = "exact match"
                        
                        is_correct, _ = self.compare_answers(parsed_answer, expected_parsed, tolerance)
                        valid_attempts.append(is_correct)
                    except:
                        valid_attempts.append(False)
                else:
                    valid_attempts.append(False)
            
            # If no valid attempts, skip this question
            if len(valid_attempts) == 0:
                if calculate_per_level:
                    level_key = str(level_id)
                    if level_key in level_total_questions:
                        level_total_questions[level_key] -= 1
                else:
                    total_questions -= 1
                continue
            
            # Calculate Pass@n
            if calculate_per_level:
                level_key = str(level_id)
                
                # Pass@1: first valid attempt is correct
                if len(valid_attempts) >= 1:
                    if valid_attempts[0]:
                        level_pass_at_1_count[level_key] += 1
                
                # Pass@2: at least one of first 2 valid attempts is correct
                if len(valid_attempts) >= 1:
                    if any(valid_attempts[:2]):
                        level_pass_at_2_count[level_key] += 1
                
                # Pass@3: at least one of first 3 valid attempts is correct
                if len(valid_attempts) >= 1:
                    if any(valid_attempts[:3]):
                        level_pass_at_3_count[level_key] += 1
            else:
                # Pass@1: first valid attempt is correct
                if len(valid_attempts) >= 1:
                    if valid_attempts[0]:
                        pass_at_1_count += 1
                
                # Pass@2: at least one of first 2 valid attempts is correct
                if len(valid_attempts) >= 1:
                    if any(valid_attempts[:2]):
                        pass_at_2_count += 1
                
                # Pass@3: at least one of first 3 valid attempts is correct
                if len(valid_attempts) >= 1:
                    if any(valid_attempts[:3]):
                        pass_at_3_count += 1
        
        # Calculate percentages
        if calculate_per_level:
            # Return per-level Pass@n
            pass_at_n = {}
            for level in level_total_questions.keys():
                total = level_total_questions[level]
                pass_at_n[level] = {
                    'pass_at_1': (level_pass_at_1_count.get(level, 0) / total * 100) if total > 0 else 0.0,
                    'pass_at_2': (level_pass_at_2_count.get(level, 0) / total * 100) if total > 0 else 0.0,
                    'pass_at_3': (level_pass_at_3_count.get(level, 0) / total * 100) if total > 0 else 0.0,
                    'total_questions_with_valid_attempts': total,
                    'pass_at_1_count': level_pass_at_1_count.get(level, 0),
                    'pass_at_2_count': level_pass_at_2_count.get(level, 0),
                    'pass_at_3_count': level_pass_at_3_count.get(level, 0)
                }
        else:
            # Return overall Pass@n
            pass_at_n = {
                'pass_at_1': (pass_at_1_count / total_questions * 100) if total_questions > 0 else 0.0,
                'pass_at_2': (pass_at_2_count / total_questions * 100) if total_questions > 0 else 0.0,
                'pass_at_3': (pass_at_3_count / total_questions * 100) if total_questions > 0 else 0.0,
                'total_questions_with_valid_attempts': total_questions,
                'pass_at_1_count': pass_at_1_count,
                'pass_at_2_count': pass_at_2_count,
                'pass_at_3_count': pass_at_3_count
            }
        
        return pass_at_n
    
    def print_detailed_differences(self, diff_info: Dict, indent: int = 0):
        """
        Recursively print detailed difference information in a readable format.
        """
        indent_str = "  " * indent
        
        if "error" in diff_info:
            print(f"{indent_str}❌ ERROR: {diff_info['error']}")
            return
        
        diff_type = diff_info.get("type", "unknown")
        
        if diff_type == "number":
            actual = diff_info.get("actual", "N/A")
            expected = diff_info.get("expected", "N/A")
            difference = diff_info.get("difference", "N/A")
            tolerance = diff_info.get("tolerance", "N/A")
            is_correct = diff_info.get("is_correct", False)
            
            status = "✅" if is_correct else "❌"
            print(f"{indent_str}{status} Number: actual={actual}, expected={expected}, diff={difference}, tolerance={tolerance}")
            
        elif diff_type == "number_exact_values":
            actual = diff_info.get("actual", "N/A")
            expected_values = diff_info.get("expected_values", [])
            is_correct = diff_info.get("is_correct", False)
            
            status = "✅" if is_correct else "❌"
            print(f"{indent_str}{status} Number (Exact Values): actual={actual}, expected_values={expected_values}")
            
        elif diff_type == "list":
            length = diff_info.get("length", 0)
            is_correct = diff_info.get("is_correct", False)
            element_diffs = diff_info.get("element_differences", [])
            
            status = "✅" if is_correct else "❌"
            print(f"{indent_str}{status} List (length={length}):")
            
            for element_diff in element_diffs:
                index = element_diff.get("index", "?")
                element_correct = element_diff.get("is_correct", False)
                element_status = "✅" if element_correct else "❌"
                print(f"{indent_str}  {element_status} Element[{index}]:")
                self.print_detailed_differences(element_diff.get("difference_info", {}), indent + 2)
                
        elif diff_type == "dict":
            keys = diff_info.get("keys", [])
            is_correct = diff_info.get("is_correct", False)
            key_diffs = diff_info.get("key_differences", [])
            
            status = "✅" if is_correct else "❌"
            print(f"{indent_str}{status} Dict (keys={keys}):")
            
            for key_diff in key_diffs:
                key = key_diff.get("key", "?")
                key_correct = key_diff.get("is_correct", False)
                key_status = "✅" if key_correct else "❌"
                print(f"{indent_str}  {key_status} Key '{key}':")
                self.print_detailed_differences(key_diff.get("difference_info", {}), indent + 2)
                
        elif diff_type in ["string", "string_exact_match", "string_list_exact_match", "exact_match", "direct"]:
            is_correct = diff_info.get("is_correct", False)
            status = "✅" if is_correct else "❌"
            print(f"{indent_str}{status} {diff_type.title()}: {'Correct' if is_correct else 'Incorrect'}")
            
        elif diff_type == "semantic_match":
            is_correct = diff_info.get("is_correct", False)
            similarity = diff_info.get("similarity", 0.0)
            threshold = diff_info.get("threshold", 0.70)
            status = "✅" if is_correct else "❌"
            print(f"{indent_str}{status} Semantic Match: similarity={similarity:.3f}, threshold={threshold}, {'Correct' if is_correct else 'Incorrect'}")
            
        elif diff_type in ["string_list_semantic_match", "semantic_match_fallback"]:
            is_correct = diff_info.get("is_correct", False)
            status = "✅" if is_correct else "❌"
            print(f"{indent_str}{status} {diff_type.title()}: {'Correct' if is_correct else 'Incorrect'}")
            
        elif diff_type == "partial_match":
            matched_length = diff_info.get("matched_length", 0)
            total_length = diff_info.get("total_length", 0)
            status = "✅"
            print(f"{indent_str}{status} Partial Match: matched {matched_length}/{total_length} elements (first {matched_length} elements correct)")
            
        elif diff_type == "partial_match_failed":
            matched_length = diff_info.get("matched_length", 0)
            total_length = diff_info.get("total_length", 0)
            element_diffs = diff_info.get("element_diffs", [])
            status = "❌"
            print(f"{indent_str}{status} Partial Match Failed: matched {matched_length}/{total_length} elements")
            
            # Show first few differences
            for i, element_diff in enumerate(element_diffs[:3]):  # Show only first 3 differences
                index = element_diff.get("index", "?")
                element_correct = element_diff.get("is_correct", False)
                element_status = "✅" if element_correct else "❌"
                print(f"{indent_str}  {element_status} Element[{index}]:")
                self.print_detailed_differences(element_diff.get("difference_info", {}), indent + 2)
            
            if len(element_diffs) > 3:
                print(f"{indent_str}  ... and {len(element_diffs) - 3} more differences")
            
        else:
            print(f"{indent_str}❓ Unknown type: {diff_type}")
    
    def evaluate_all_questions(self) -> Dict:
        """Evaluate all questions from results JSON and calculate success rate metrics."""
        
        evaluation_results = {
            'timestamp': datetime.now().isoformat(),
            'total_questions': 0,
            'correct_answers': 0,
            'question_results': [],
            'success_rate': 0.0,  
            'completion_rate': 0.0,  # for workflow completion
            'level_success_rate': {},
            'pass_at_n': {},  # Pass@1, Pass@2, Pass@3 metrics
            'category': self._extract_category_from_filename(os.path.basename(self.results_json_path)),
            'average_execution_time': 0.0,  # Average time in seconds
            'total_execution_time': 0.0     # Total time in seconds
        }
        
        # Group results by question content and level
        question_groups = {}
        for result in self.results_data:
            level_id = result.get('level_id', 0)
            question = result.get('question', '')
            # Use a combination of level_id and question to identify unique questions
            key = (level_id, question)
            if key not in question_groups:
                question_groups[key] = []
            question_groups[key].append(result)
        
        # Process each question group with proper question numbering
        # First, create a mapping from question to question number
        question_to_number = {}
        question_number = 1
        for (level_id, question), results in question_groups.items():
            if question not in question_to_number:
                question_to_number[question] = question_number
                question_number += 1
        
        # Now process each group with the correct question number
        for (level_id, question), results in question_groups.items():
            # Get the first result to extract common information
            first_result = results[0]
            expected_answer_str = first_result.get('answer', 'N/A')
            expected_answer = self._parse_result(expected_answer_str)
            tolerance_str = first_result.get('tolerance', '0')
            tolerance = self._parse_tolerance(tolerance_str)

            # Special case: if expected_answer is a string or list of strings and tolerance is 0, set to 'exact match'
            # But don't override if tolerance is already set to 'semantic_match'
            def is_str_or_list_of_str(x):
                if isinstance(x, str):
                    return True
                if isinstance(x, list) and all(isinstance(i, str) for i in x):
                    return True
                return False
            if is_str_or_list_of_str(expected_answer) and (tolerance == 0 or tolerance == 0.0) and tolerance != "semantic_match":
                tolerance = "exact match"
            
            extracted_answers = []
            correct_count = 0
            total_count = len(results)
            actual_counted_attempts = 0  # Track attempts that are actually counted
            detailed_differences = []
            question_execution_times = []  # Track execution times for this question
            
            print(f"\n{'='*60}")
            print(f"QUESTION {question_to_number[question]} (Level {level_id})")
            print(f"{'='*60}")
            print(f"Expected Answer: {expected_answer}")
            print(f"Tolerance: {tolerance}")
            print(f"Total Attempts: {total_count}")
            print()
            
            for i, result in enumerate(results):
                processed_output = result.get('processed_output', '')
                
                print(f"Attempt {i+1}:")
                
                # Skip "Workflow Failed" attempts
                if processed_output == "Workflow Failed":
                    print(f"  ⏭️  WORKFLOW FAILED - Skipping from success rate calculation")
                    print()
                    continue
                
                # Increment the counter for attempts that are actually counted
                actual_counted_attempts += 1
                
                # Collect execution time if available (excluding workflow failed)
                execution_time = result.get('execution_time_seconds')
                if execution_time is not None:
                    question_execution_times.append(execution_time)
                    evaluation_results['total_execution_time'] += execution_time
                
                # Parse the processed output
                if processed_output and processed_output.lower() != 'failed':
                    try:
                        parsed_answer = self._parse_result(processed_output)
                        extracted_answers.append(parsed_answer)
                        
                        is_correct, diff_info = self.compare_answers(parsed_answer, expected_answer, tolerance)
                        detailed_differences.append(diff_info)
                        
                        if is_correct:
                            correct_count += 1
                            print(f"  ✅ CORRECT")
                        else:
                            print(f"  ❌ INCORRECT - Detailed differences:")
                            self.print_detailed_differences(diff_info, indent=2)
                            
                    except Exception as e:
                        extracted_answers.append(None)
                        detailed_differences.append({"error": f"Parsing error: {str(e)}"})
                        print(f"  ❌ PARSING ERROR: {str(e)}")
                else:
                    extracted_answers.append(None)
                    detailed_differences.append({"error": "Failed or empty output"})
                    print(f"  ❌ FAILED OR EMPTY OUTPUT")
                
                print()
            
            # Calculate success rate percentage based on actual counted attempts
            success_rate_percent = (correct_count / actual_counted_attempts * 100) if actual_counted_attempts > 0 else 0.0
            
            # Calculate average execution time for this question
            avg_execution_time = sum(question_execution_times) / len(question_execution_times) if question_execution_times else 0.0
            
            print(f"SUMMARY: {correct_count}/{actual_counted_attempts} correct ({success_rate_percent:.2f}%)")
            if question_execution_times:
                print(f"AVERAGE EXECUTION TIME: {avg_execution_time:.2f} seconds")
            if actual_counted_attempts < total_count:
                print(f"NOTE: {total_count - actual_counted_attempts} attempts were skipped due to 'Workflow Failed'")
            
            question_result = {
                'question_number': question_to_number[question],
                'question_key': str(level_id),
                'expected_answer': expected_answer, 
                'tolerance': tolerance,
                'extracted_answers': extracted_answers,
                'detailed_differences': detailed_differences,
                'correct_count': correct_count,
                'total_count': actual_counted_attempts,  # Use actual counted attempts
                'success_rate_percent': success_rate_percent,
                'average_execution_time': avg_execution_time,
                'execution_times': question_execution_times
            }
            
            evaluation_results['question_results'].append(question_result)
            evaluation_results['total_questions'] += actual_counted_attempts  # Use actual counted attempts
            evaluation_results['correct_answers'] += correct_count
        
        # Calculate completion rate: successful workflows / total attempts
        total_attempts = len(self.results_data)
        evaluation_results['completion_rate'] = (evaluation_results['total_questions'] / total_attempts * 100) if total_attempts > 0 else 0.0
        
        # Calculate success rate: correct answers / successful workflows
        if evaluation_results['total_questions'] > 0:
            evaluation_results['success_rate'] = (
                evaluation_results['correct_answers'] / evaluation_results['total_questions'] * 100
            )
        
        # Calculate overall average execution time (excluding workflow failed)
        total_time_count = sum(len(qr['execution_times']) for qr in evaluation_results['question_results'])
        if total_time_count > 0:
            evaluation_results['average_execution_time'] = evaluation_results['total_execution_time'] / total_time_count
        
        # Calculate level-specific success rate
        evaluation_results['level_success_rate'] = self._calculate_level_success_rate(self.results_data)
        
        # Calculate Pass@n metrics (overall)
        evaluation_results['pass_at_n'] = self._calculate_pass_at_n(self.results_data, calculate_per_level=False)
        
        # Calculate Pass@n metrics per level
        evaluation_results['level_pass_at_n'] = self._calculate_pass_at_n(self.results_data, calculate_per_level=True)
        
        return evaluation_results
    
    def print_evaluation_summary(self, results: Dict):
        """Print formatted evaluation summary with percentages."""
        print(f"\n{'='*60}")
        print("UNIVERSAL BENCHMARK EVALUATION SUMMARY")
        print(f"{'='*60}")
        print(f"Evaluation Time: {results['timestamp']}")
        print(f"Category: {results.get('category', 'Unknown')}")
        print(f"Total Questions: {results['total_questions']}")
        print(f"Correct Answers: {results['correct_answers']}")
        print(f"Success Rate: {results['success_rate']:.2f}%")
        print(f"Completion Rate: {results['completion_rate']:.2f}%")
        if results.get('average_execution_time', 0) > 0:
            print(f"Average Execution Time: {results['average_execution_time']:.2f} seconds")
        
        # Print Pass@n metrics
        if 'pass_at_n' in results and results['pass_at_n']:
            pass_at_n = results['pass_at_n']
            print(f"\n{'='*60}")
            print("PASS@N METRICS")
            print(f"{'='*60}")
            print(f"Pass@1: {pass_at_n['pass_at_1']:.2f}% ({pass_at_n['pass_at_1_count']}/{pass_at_n['total_questions_with_valid_attempts']} questions)")
            print(f"Pass@2: {pass_at_n['pass_at_2']:.2f}% ({pass_at_n['pass_at_2_count']}/{pass_at_n['total_questions_with_valid_attempts']} questions)")
            print(f"Pass@3: {pass_at_n['pass_at_3']:.2f}% ({pass_at_n['pass_at_3_count']}/{pass_at_n['total_questions_with_valid_attempts']} questions)")
        
        # Print level-specific metrics
        if 'level_success_rate' in results:
            print(f"\n{'='*60}")
            print("LEVEL-SPECIFIC METRICS")
            print(f"{'='*60}")
            for level, stats in sorted(results['level_success_rate'].items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
                print(f"Level {level}:")
                print(f"  Success Rate: {stats['success_rate']:.2f}% ({stats['correct']}/{stats['total']} correct)")
                print(f"  Completion Rate: {stats['completion_rate']:.2f}% ({stats['total']}/{stats['total_attempts']} completed)")
                if stats.get('average_execution_time', 0) > 0:
                    print(f"  Average Execution Time: {stats['average_execution_time']:.2f} seconds")
                
                # Print Pass@n for this level
                if 'level_pass_at_n' in results and level in results['level_pass_at_n']:
                    level_pass_n = results['level_pass_at_n'][level]
                    print(f"  Pass@1: {level_pass_n['pass_at_1']:.2f}%, "
                          f"Pass@2: {level_pass_n['pass_at_2']:.2f}%, "
                          f"Pass@3: {level_pass_n['pass_at_3']:.2f}%")
        
        print(f"\n{'='*60}")
        print("PER-QUESTION RESULTS")
        print(f"{'='*60}")
        
        for question_result in results['question_results']:
            print(f"\nQuestion {question_result['question_number']} (Key {question_result['question_key']}):")
            print(f"  Expected: {question_result['expected_answer']}")
            print(f"  Tolerance: {question_result['tolerance']}")
            print(f"  Success Rate: {question_result['success_rate_percent']:.2f}% "
                  f"({question_result['correct_count']}/{question_result['total_count']})")
            if question_result.get('average_execution_time', 0) > 0:
                print(f"  Avg Time: {question_result['average_execution_time']:.2f} seconds")
    
    def save_detailed_results(self, results: Dict, output_file: str = None):
        """Save detailed results to JSON file."""
        if output_file is None:
            output_file = f"benchmark_evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        serializable_results = json.loads(json.dumps(results, default=str))
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        print(f"\nDetailed results saved to: {output_file}")

    def _compare_recursive(self, actual: Any, expected: Any, tolerance: Union[float, int, list]) -> bool:
        """
        Backward-compatible recursive comparison method.
        Returns only the boolean result for compatibility with existing code.
        """
        is_correct, _ = self._compare_recursive_with_diff(actual, expected, tolerance)
        return is_correct

    def _compare_numbers(self, actual: Union[int, float], expected: Union[int, float], 
                        tolerance: Union[int, float, list]) -> bool:
        """
        Backward-compatible number comparison method.
        Returns only the boolean result for compatibility with existing code.
        """
        is_correct, _ = self._compare_numbers_with_diff(actual, expected, tolerance)
        return is_correct

    def _compare_lists(self, actual: List, expected: List, tolerance: Union[float, int, list]) -> bool:
        """
        Backward-compatible list comparison method.
        Returns only the boolean result for compatibility with existing code.
        """
        is_correct, _ = self._compare_lists_with_diff(actual, expected, tolerance)
        return is_correct

    def _compare_dicts(self, actual: dict, expected: dict, tolerance: Union[float, int]) -> bool:
        """
        Backward-compatible dict comparison method.
        Returns only the boolean result for compatibility with existing code.
        """
        is_correct, _ = self._compare_dicts_with_diff(actual, expected, tolerance)
        return is_correct
    
    def _calculate_string_similarity(self, actual: str, expected: str) -> float:
        """
        Calculate similarity between two strings based on common content.
        Optimized for robocrystallographer crystal structure descriptions.
        """
        if not actual or not expected:
            return 0.0
        
        # Handle failed outputs
        if actual.lower() in ['failed', 'error', 'none', 'null']:
            return 0.0
        
        # Normalize strings: remove extra whitespace, convert to lowercase
        actual_norm = ' '.join(actual.lower().split())
        expected_norm = ' '.join(expected.lower().split())
        
        if actual_norm == expected_norm:
            return 1.0
        
        # Simple normalization for common format differences
        def normalize_format(text):
            # Remove Å symbols
            text = text.replace('å', ' ').replace('Å', ' ')
            # Normalize subscripts and superscripts
            text = text.replace('₂', '2').replace('₆', '6').replace('₄', '4')
            text = text.replace('⁴⁺', '4+').replace('²⁻', '2-')
            # Remove degree symbols
            text = text.replace('°', '')
            # Normalize underscores in space groups
            text = text.replace('_', '')
            # Remove extra spaces
            text = ' '.join(text.split())
            return text
        
        actual_clean = normalize_format(actual_norm)
        expected_clean = normalize_format(expected_norm)
        
        if actual_clean == expected_clean:
            return 1.0
        
        # Calculate word-based similarity
        actual_words = set(actual_clean.split())
        expected_words = set(expected_clean.split())
        
        if not actual_words or not expected_words:
            return 0.0
        
        # Calculate Jaccard similarity
        intersection = len(actual_words.intersection(expected_words))
        union = len(actual_words.union(expected_words))
        return intersection / union if union > 0 else 0.0
    
    def _compare_string_lists_semantic(self, actual: List[str], expected: List[str]) -> bool:
        """
        Compare string lists using semantic matching.
        Returns True if most elements match semantically.
        """
        if len(actual) != len(expected):
            return False
        
        # Calculate similarity for each pair of strings
        similarities = []
        for a, e in zip(actual, expected):
            similarity = self._calculate_string_similarity(a, e)
            similarities.append(similarity)
        
        # Check if average similarity is above threshold
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        return avg_similarity >= 0.70  # 70% threshold


def evaluate_all_benchmarks(results_dir: str):
    """Evaluate all results JSON files in a directory."""
    results_files = [f for f in os.listdir(results_dir) if f.startswith("results_") and f.endswith(".json")]
    all_correct = 0
    all_total = 0
    total_attempts_all = 0  # Track total attempts from all benchmarks
    per_benchmark = {}
    all_results = {
        'timestamp': datetime.now().isoformat(),
        'results_directory': results_dir,
        'benchmarks': {},
        'summary': {},
        'category_summary': {},
        'level_summary': {'0': {'correct': 0, 'total': 0, 'total_attempts': 0, 'execution_times': []}, 
                         '1': {'correct': 0, 'total': 0, 'total_attempts': 0, 'execution_times': []}},
        'overall_average_execution_time': 0.0,
        'overall_total_execution_time': 0.0
    }

    for results_file in results_files:
        benchmark_name = results_file.replace("results_", "").replace(".json", "")
        results_path = os.path.join(results_dir, results_file)
        
        print(f"\n=== Evaluating {benchmark_name} ===")
        evaluator = UniversalBenchmarkEvaluator(results_path)
        results = evaluator.evaluate_all_questions()
        evaluator.print_evaluation_summary(results)
        
        # Track total attempts from this benchmark
        total_attempts_all += len(evaluator.results_data)
        
        # Save individual benchmark results
        all_results['benchmarks'][benchmark_name] = results
        
        per_benchmark[benchmark_name] = {
            "correct": results["correct_answers"],
            "total": results["total_questions"],
            "success_rate": results["success_rate"],
            "completion_rate": results["completion_rate"],
            "level_success_rate": results.get("level_success_rate", {}),
            "average_execution_time": results.get("average_execution_time", 0.0),
            "pass_at_n": results.get("pass_at_n", {}),
            "level_pass_at_n": results.get("level_pass_at_n", {})
        }
        all_correct += results["correct_answers"]
        all_total += results["total_questions"]
        all_results['overall_total_execution_time'] += results.get('total_execution_time', 0.0)
        
        # Aggregate level-specific statistics
        if 'level_success_rate' in results:
            for level, stats in results['level_success_rate'].items():
                if level not in all_results['level_summary']:
                    all_results['level_summary'][level] = {'correct': 0, 'total': 0, 'total_attempts': 0, 'execution_times': []}
                all_results['level_summary'][level]['correct'] += stats['correct']
                all_results['level_summary'][level]['total'] += stats['total']
                all_results['level_summary'][level]['total_attempts'] += stats['total_attempts']
                all_results['level_summary'][level]['execution_times'].extend(stats['execution_times'])

    # Calculate overall level metrics
    for level in all_results['level_summary']:
        total = all_results['level_summary'][level]['total']
        correct = all_results['level_summary'][level]['correct']
        total_attempts = all_results['level_summary'][level]['total_attempts']
        execution_times = all_results['level_summary'][level]['execution_times']
        
        all_results['level_summary'][level]['success_rate'] = (correct / total * 100) if total > 0 else 0.0
        all_results['level_summary'][level]['completion_rate'] = (total / total_attempts * 100) if total_attempts > 0 else 0.0
        all_results['level_summary'][level]['average_execution_time'] = (sum(execution_times) / len(execution_times)) if execution_times else 0.0

    # Calculate overall average execution time
    total_time_samples = sum(
        len(qr['execution_times']) 
        for benchmark_results in all_results['benchmarks'].values()
        for qr in benchmark_results.get('question_results', [])
    )
    if total_time_samples > 0:
        all_results['overall_average_execution_time'] = all_results['overall_total_execution_time'] / total_time_samples
    
    # Calculate overall completion rate and success rate
    
    overall_completion_rate = (all_total / total_attempts_all * 100) if total_attempts_all > 0 else 0.0
    overall_success_rate = (all_correct / all_total * 100) if all_total > 0 else 0.0
    
    # Calculate overall Pass@n metrics by aggregating from all benchmarks
    overall_pass_at_1_count = sum(b['pass_at_n'].get('pass_at_1_count', 0) for b in per_benchmark.values() if 'pass_at_n' in b)
    overall_pass_at_2_count = sum(b['pass_at_n'].get('pass_at_2_count', 0) for b in per_benchmark.values() if 'pass_at_n' in b)
    overall_pass_at_3_count = sum(b['pass_at_n'].get('pass_at_3_count', 0) for b in per_benchmark.values() if 'pass_at_n' in b)
    overall_questions_with_valid = sum(b['pass_at_n'].get('total_questions_with_valid_attempts', 0) for b in per_benchmark.values() if 'pass_at_n' in b)
    
    overall_pass_at_n = {
        'pass_at_1': (overall_pass_at_1_count / overall_questions_with_valid * 100) if overall_questions_with_valid > 0 else 0.0,
        'pass_at_2': (overall_pass_at_2_count / overall_questions_with_valid * 100) if overall_questions_with_valid > 0 else 0.0,
        'pass_at_3': (overall_pass_at_3_count / overall_questions_with_valid * 100) if overall_questions_with_valid > 0 else 0.0,
        'total_questions_with_valid_attempts': overall_questions_with_valid,
        'pass_at_1_count': overall_pass_at_1_count,
        'pass_at_2_count': overall_pass_at_2_count,
        'pass_at_3_count': overall_pass_at_3_count
    }
    
    # Calculate level-specific Pass@n metrics by aggregating from all benchmarks
    overall_level_pass_at_n = {}
    for benchmark_stats in per_benchmark.values():
        if 'level_pass_at_n' in benchmark_stats:
            for level, level_pass_n in benchmark_stats['level_pass_at_n'].items():
                if level not in overall_level_pass_at_n:
                    overall_level_pass_at_n[level] = {
                        'pass_at_1_count': 0,
                        'pass_at_2_count': 0,
                        'pass_at_3_count': 0,
                        'total_questions_with_valid_attempts': 0
                    }
                overall_level_pass_at_n[level]['pass_at_1_count'] += level_pass_n.get('pass_at_1_count', 0)
                overall_level_pass_at_n[level]['pass_at_2_count'] += level_pass_n.get('pass_at_2_count', 0)
                overall_level_pass_at_n[level]['pass_at_3_count'] += level_pass_n.get('pass_at_3_count', 0)
                overall_level_pass_at_n[level]['total_questions_with_valid_attempts'] += level_pass_n.get('total_questions_with_valid_attempts', 0)
    
    # Calculate percentages for level-specific Pass@n
    for level in overall_level_pass_at_n:
        total = overall_level_pass_at_n[level]['total_questions_with_valid_attempts']
        if total > 0:
            overall_level_pass_at_n[level]['pass_at_1'] = (overall_level_pass_at_n[level]['pass_at_1_count'] / total * 100)
            overall_level_pass_at_n[level]['pass_at_2'] = (overall_level_pass_at_n[level]['pass_at_2_count'] / total * 100)
            overall_level_pass_at_n[level]['pass_at_3'] = (overall_level_pass_at_n[level]['pass_at_3_count'] / total * 100)
        else:
            overall_level_pass_at_n[level]['pass_at_1'] = 0.0
            overall_level_pass_at_n[level]['pass_at_2'] = 0.0
            overall_level_pass_at_n[level]['pass_at_3'] = 0.0
    
    # Create summary
    all_results['summary'] = {
        'total_benchmarks': len(results_files),
        'total_questions': all_total,
        'total_correct': all_correct,
        'overall_success_rate': overall_success_rate,
        'overall_completion_rate': overall_completion_rate,
        'average_execution_time': all_results['overall_average_execution_time'],
        'overall_pass_at_n': overall_pass_at_n,
        'overall_level_pass_at_n': overall_level_pass_at_n,
        'per_benchmark': per_benchmark
    }

    print("\n=== SUMMARY ===")
    for name, stats in per_benchmark.items():
        print(f"{name}: {stats['correct']}/{stats['total']} correct, Success Rate: {stats['success_rate']:.2f}%, Completion Rate: {stats['completion_rate']:.2f}%")
        if stats.get('average_execution_time', 0) > 0:
            print(f"  Average Execution Time: {stats['average_execution_time']:.2f} seconds")
        if 'pass_at_n' in stats and stats['pass_at_n']:
            pass_at_n = stats['pass_at_n']
            print(f"  Pass@1: {pass_at_n['pass_at_1']:.2f}%, Pass@2: {pass_at_n['pass_at_2']:.2f}%, Pass@3: {pass_at_n['pass_at_3']:.2f}%")
        if 'level_success_rate' in stats:
            for level, level_stats in stats['level_success_rate'].items():
                print(f"  Level {level}: Success Rate: {level_stats['success_rate']:.2f}%, "
                      f"Completion Rate: {level_stats['completion_rate']:.2f}%")
                if level_stats.get('average_execution_time', 0) > 0:
                    print(f"    Average Execution Time: {level_stats['average_execution_time']:.2f} seconds")
    
    if all_total > 0:
        print(f"\nTOTAL: {all_correct}/{all_total} correct, Overall Success Rate: {overall_success_rate:.2f}%, Overall Completion Rate: {overall_completion_rate:.2f}%")
        if all_results['overall_average_execution_time'] > 0:
            print(f"Overall Average Execution Time: {all_results['overall_average_execution_time']:.2f} seconds")
        
        # Print overall Pass@n metrics
        if overall_questions_with_valid > 0:
            print(f"\n{'='*60}")
            print("OVERALL PASS@N METRICS")
            print(f"{'='*60}")
            print(f"Pass@1: {overall_pass_at_n['pass_at_1']:.2f}% ({overall_pass_at_n['pass_at_1_count']}/{overall_pass_at_n['total_questions_with_valid_attempts']} questions)")
            print(f"Pass@2: {overall_pass_at_n['pass_at_2']:.2f}% ({overall_pass_at_n['pass_at_2_count']}/{overall_pass_at_n['total_questions_with_valid_attempts']} questions)")
            print(f"Pass@3: {overall_pass_at_n['pass_at_3']:.2f}% ({overall_pass_at_n['pass_at_3_count']}/{overall_pass_at_n['total_questions_with_valid_attempts']} questions)")
        
        # Print overall level summary
        print(f"\n{'='*60}")
        print("OVERALL LEVEL SUMMARY")
        print(f"{'='*60}")
        for level, stats in sorted(all_results['level_summary'].items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
            print(f"Level {level}: Success Rate: {stats['success_rate']:.2f}%, Completion Rate: {stats['completion_rate']:.2f}%")
            if stats.get('average_execution_time', 0) > 0:
                print(f"  Average Execution Time: {stats['average_execution_time']:.2f} seconds")
            
            # Print level-specific Pass@n
            if level in overall_level_pass_at_n:
                level_pass_n = overall_level_pass_at_n[level]
                print(f"  Pass@1: {level_pass_n['pass_at_1']:.2f}%, "
                      f"Pass@2: {level_pass_n['pass_at_2']:.2f}%, "
                      f"Pass@3: {level_pass_n['pass_at_3']:.2f}%")
    else:
        print("No results found.")
    
    return all_results

if __name__ == "__main__":
    import argparse
    import glob
    parser = argparse.ArgumentParser(description="Evaluate benchmark results from a directory or a single results file.")
    parser.add_argument('--results-dir', type=str, help="Path to results directory")
    parser.add_argument('--results-file', type=str, help="Path to a single results JSON file to evaluate")
    args = parser.parse_args()

    # Always use benchmark subdirectories
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    BASE_RESULTS_DIR = os.path.join(PROJECT_ROOT, "test_results")
    BASE_EVAL_DIR = os.path.join(PROJECT_ROOT, "evaluation_and_accuracy")
    os.makedirs(BASE_EVAL_DIR, exist_ok=True)

    if args.results_file:
        # Evaluate a single results file
        if not os.path.exists(args.results_file):
            print(f"Specified results file does not exist: {args.results_file}")
            exit(1)
        evaluator = UniversalBenchmarkEvaluator(args.results_file)
        results = evaluator.evaluate_all_questions()
        evaluator.print_evaluation_summary(results)
        # Save to evaluation_and_accuracy
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(BASE_EVAL_DIR, f"benchmark_evaluation_{timestamp}.json")
        evaluator.save_detailed_results(results, output_file=output_file)
    else:
        # If no results directory specified, try to find the most recent one in test_results
        if not args.results_dir:
            results_dirs = glob.glob(os.path.join(BASE_RESULTS_DIR, "results_*"))
            if results_dirs:
                # Sort by modification time and use the most recent
                results_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                args.results_dir = results_dirs[0]
                print(f"Using most recent results directory: {args.results_dir}")
            else:
                print("No results directories found in test_results. Please specify --results-dir or --results-file manually.")
                exit(1)
        # Evaluate all benchmarks in the specified directory
        all_results = evaluate_all_benchmarks(args.results_dir)
        # Save to evaluation_and_accuracy
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(BASE_EVAL_DIR, f"benchmark_evaluation_{timestamp}.json")
        serializable_results = json.loads(json.dumps(all_results, default=str))
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        print(f"\nDetailed results saved to: {output_file}")