import json
import re
import os
from typing import List, Dict, Any, Optional

class NarrationRulesEngine:
    """
    Applies configurable rules to map bank statement narrations to specific Tally Ledgers.
    Supports 'contains', 'exact', and 'regex' matching types.
    """
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.rules: List[Dict[str, str]] = []
        self.default_ledger: str = "SUSPENS"
        
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)
        else:
            self._load_default_rules()

    def _load_default_rules(self):
        """Default rules for common Indian banking narrations."""
        self.rules = [
            {"pattern": "MANEESH", "match_type": "contains", "ledger": "Maneesh Account"},
            {"pattern": "Shar ad K|SHAR AD K|Sharad K", "match_type": "regex", "ledger": "Sharad K Account"},
            {"pattern": "POS Rent|Pos Basic_Service_Fee|POS COMMITMENTCHARGE", "match_type": "regex", "ledger": "POS Machine Charges"},
            {"pattern": "GUPTA BUILDING MATERIA", "match_type": "contains", "ledger": "Gupta Building Material"},
            {"pattern": "CEMTEX", "match_type": "contains", "ledger": "Cemtex Trading Co"},
            {"pattern": "SI FAIL|CHARGES|CHEQUE BOOK|AC KEEPING FEES", "match_type": "regex", "ledger": "Bank Charges"},
            {"pattern": "JAI MAA LAXMI", "match_type": "contains", "ledger": "Jai Maa Laxmi Enterprises"},
            {"pattern": "DHRUV TRADERS", "match_type": "contains", "ledger": "Dhruv Traders"},
            {"pattern": "CASH WITHDRAWAL", "match_type": "contains", "ledger": "Cash Account"}
        ]

    def load_config(self, filepath: str):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.rules = data.get("rules", [])
                self.default_ledger = data.get("default_ledger", "SUSPENS")
                self.config_path = filepath
        except Exception as e:
            print(f"Error loading rules config: {e}")

    def save_config(self, filepath: Optional[str] = None):
        save_path = filepath or self.config_path or "narration_rules.json"
        data = {
            "default_ledger": self.default_ledger,
            "rules": self.rules
        }
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def add_rule(self, pattern: str, ledger: str, match_type: str = "contains"):
        self.rules.append({
            "pattern": pattern,
            "match_type": match_type,
            "ledger": ledger
        })

    def match_ledger(self, narration: str, fallback: str = "SUSPENS") -> str:
        if not narration:
            return fallback or self.default_ledger

        narration_clean = str(narration).strip()

        for rule in self.rules:
            pattern = rule.get("pattern", "")
            match_type = rule.get("match_type", "contains")
            ledger = rule.get("ledger", "")

            if not pattern or not ledger:
                continue

            if match_type == "contains":
                if pattern.lower() in narration_clean.lower():
                    return ledger
            elif match_type == "exact":
                if pattern.lower() == narration_clean.lower():
                    return ledger
            elif match_type == "regex":
                try:
                    if re.search(pattern, narration_clean, re.IGNORECASE):
                        return ledger
                except re.error:
                    pass

        return fallback or self.default_ledger
