import json
import requests
from typing import Dict, Any, List, Optional

class LLMColumnMapper:
    """
    Auto-detects bank statement column mappings using any OpenAI-compatible API endpoint
    (OpenAI, Groq, Ollama, LM Studio, OpenRouter, vLLM, DeepSeek, etc.).
    """
    def __init__(self, api_key: str = "", base_url: str = "https://api.openai.com/v1", model_name: str = "gpt-4o-mini"):
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip('/')
        self.model_name = model_name.strip()

    def auto_map_columns(self, headers: List[str], sample_rows: List[List[str]]) -> Dict[str, Optional[int]]:
        """
        Queries the LLM with statement headers and sample rows to infer column indices.
        Returns a dictionary mapping required field names to column indices (0-based) or None.
        """
        prompt = f"""
You are an expert accounting system AI.
Analyze these bank statement table headers and sample data rows extracted from a PDF statement.

Headers:
{headers}

Sample Rows:
{sample_rows}

Map the 0-based column index for each required Tally field:
1. "date": Date of transaction (Post Date or Date)
2. "value_date": Value Date (or null if absent)
3. "narration": Description, Particulars, Transaction Details
4. "cheque_no": Cheque Number, Ref No, UTR, Instrument Number (or null if absent)
5. "debit": Debit Amount, Withdrawal, Dr
6. "credit": Credit Amount, Deposit, Cr
7. "balance": Running Balance

Return ONLY a raw JSON object with 0-based integer column indices (or null).
Do NOT include markdown formatting or extra text.

Example JSON output:
{{
  "date": 0,
  "value_date": 1,
  "narration": 2,
  "cheque_no": 3,
  "debit": 4,
  "credit": 5,
  "balance": 6
}}
"""

        endpoint = f"{self.base_url}/chat/completions"
        headers_req = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers_req["Authorization"] = f"Bearer {self.api_key}"
        elif "openai.com" in self.base_url:
            raise ValueError("API Key is required for OpenAI endpoint.")
        else:
            headers_req["Authorization"] = "Bearer dummy"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a JSON generator. Respond ONLY with valid raw JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0
        }

        try:
            resp = requests.post(endpoint, json=payload, headers=headers_req, timeout=25)
            resp.raise_for_status()
            res_data = resp.json()

            content = res_data['choices'][0]['message']['content'].strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()

            parsed_mapping = json.loads(content)
            return parsed_mapping

        except Exception as e:
            raise RuntimeError(f"LLM API Call failed ({self.base_url}): {str(e)}")
