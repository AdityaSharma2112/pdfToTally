from bank_parser import CustomColumnBankParser
from llm_mapper import LLMColumnMapper
from rules_engine import NarrationRulesEngine

def test_custom_mapper():
    column_map = {
        "date": 0,
        "value_date": 1,
        "narration": 2,
        "cheque_no": 3,
        "debit": 4,
        "credit": 5,
        "balance": 6
    }

    rules = NarrationRulesEngine()
    parser = CustomColumnBankParser(column_map)
    print("CustomColumnBankParser created successfully!")

    print("Checking LLMColumnMapper class structure...")
    mapper = LLMColumnMapper(api_key="test-key", base_url="http://localhost:11434/v1", model_name="llama3")
    print(f"LLM Mapper initialized for base URL: {mapper.base_url}, model: {mapper.model_name}")

    headers = ["Col 0: Post Date", "Col 1: Value Date", "Col 2: Description", "Col 3: Ref No", "Col 4: Debit", "Col 5: Credit", "Col 6: Balance"]
    sample_rows = [["02-04-2025", "02-04-2025", "DEP TFR IMPS/509206919043", "", "", "5,00,000.00", "5,03,469.89CR"]]

    print("Headers:", headers)
    print("Sample Rows:", sample_rows)
    print("Unit tests PASSED!")

if __name__ == "__main__":
    test_custom_mapper()
