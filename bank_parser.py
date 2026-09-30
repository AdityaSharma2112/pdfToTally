import re
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None


class BaseBankParser:
    """Base class for bank statement parsers."""
    bank_name = "Generic Bank"

    def parse(self, pdf_path: str, rules_engine: Optional[Any] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        raise NotImplementedError

    def _clean_amount(self, amt_str: Any) -> float:
        if not amt_str:
            return 0.0
        cleaned = str(amt_str).replace(',', '').replace('CR', '').replace('DR', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0


class SBIBankParser(BaseBankParser):
    """Parser specifically optimized for State Bank of India (SBI) statements."""
    bank_name = "State Bank of India"

    def parse(self, pdf_path: str, rules_engine: Optional[Any] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        self.rules_engine = rules_engine
        metadata = {
            "bank_name": "State Bank of India",
            "account_no": "",
            "ifsc_code": "SBIN0000590",
            "account_name": "",
            "statement_period": ""
        }
        transactions = []

        text_content = ""
        pages_text = []

        if pdfplumber:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text() or ""
                        pages_text.append(t)
                text_content = "\n".join(pages_text)
            except Exception:
                pass

        if not text_content and fitz:
            try:
                doc = fitz.open(pdf_path)
                for page in doc:
                    pages_text.append(page.get_text("text"))
                text_content = "\n".join(pages_text)
            except Exception:
                pass

        if not text_content and PyPDF2:
            try:
                reader = PyPDF2.PdfReader(pdf_path)
                for page in reader.pages:
                    pages_text.append(page.extract_text() or "")
                text_content = "\n".join(pages_text)
            except Exception:
                pass

        # Extract metadata
        acc_match = re.search(r'Account\s*No\.?\s*:?\s*(\d{10,18})', text_content, re.IGNORECASE)
        if acc_match:
            metadata["account_no"] = acc_match.group(1)

        name_match = re.search(r'STATEMENT\s+OF\s+ACCOUNT\s*\n\s*([^\n]+)', text_content, re.IGNORECASE)
        if name_match:
            metadata["account_name"] = name_match.group(1).strip()

        ifsc_match = re.search(r'IFSC\s*Code\s*:?\s*([A-Z0-9]{11})', text_content, re.IGNORECASE)
        if ifsc_match:
            metadata["ifsc_code"] = ifsc_match.group(1)

        stmt_period = re.search(r'Statement\s+From\s*:?\s*([^\n]+)', text_content, re.IGNORECASE)
        if stmt_period:
            metadata["statement_period"] = stmt_period.group(1).strip()

        # 1. Try PDF table extraction if pdfplumber is available
        if pdfplumber:
            try:
                transactions = self._parse_with_pdfplumber(pdf_path)
                if transactions and len(transactions) > 0:
                    return metadata, transactions
            except Exception:
                pass

        # 2. Text parsing fallback
        transactions = self._parse_from_text(text_content)
        return metadata, transactions

    def _parse_with_pdfplumber(self, pdf_path: str) -> List[Dict[str, Any]]:
        transactions = []
        date_pattern = re.compile(r'^\d{2}-\d{2}-\d{4}$')

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 5:
                            continue
                        post_date = (row[0] or "").strip()
                        if not date_pattern.match(post_date):
                            continue

                        val_date = (row[1] or "").strip() if len(row) > 1 else post_date
                        desc = (row[2] or "").strip() if len(row) > 2 else ""
                        chq_no = (row[3] or "").strip() if len(row) > 3 else ""
                        debit_raw = (row[4] or "").strip() if len(row) > 4 else ""
                        credit_raw = (row[5] or "").strip() if len(row) > 5 else ""
                        balance_raw = (row[6] or "").strip() if len(row) > 6 else ""

                        debit = self._clean_amount(debit_raw)
                        credit = self._clean_amount(credit_raw)
                        balance = self._clean_amount(balance_raw)
                        desc_clean = " ".join(desc.split())

                        counter_ledger = "SUSPENS"
                        if hasattr(self, 'rules_engine') and self.rules_engine:
                            counter_ledger = self.rules_engine.match_ledger(desc_clean)

                        transactions.append({
                            "date": post_date,
                            "value_date": val_date,
                            "narration": desc_clean,
                            "cheque_no": chq_no,
                            "debit": debit,
                            "credit": credit,
                            "balance": balance,
                            "counter_ledger": counter_ledger
                        })
        return transactions

    def _parse_from_text(self, text: str) -> List[Dict[str, Any]]:
        transactions = []
        lines = text.split('\n')
        date_regex = re.compile(r'^(\d{2}[-/.]\d{2}[-/.]\d{2,4})\s*(?:\|\s*)?(\d{2}[-/.]\d{2}[-/.]\d{2,4})\s*(?:\|\s*)?(.+)')
        
        current_tx = None

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            match = date_regex.match(line_str)
            if match:
                if current_tx:
                    transactions.append(self._finalize_tx(current_tx))

                post_date = match.group(1)
                val_date = match.group(2)
                rest = match.group(3)

                current_tx = {
                    "date": post_date,
                    "value_date": val_date,
                    "text_body": rest
                }
            elif current_tx:
                if any(k in line_str.upper() for k in ["BROUGHT FORWARD", "STATEMENT SUMMARY", "PAGE NO.", "CLOSING BALANCE"]):
                    transactions.append(self._finalize_tx(current_tx))
                    current_tx = None
                else:
                    current_tx["text_body"] += " " + line_str

        if current_tx:
            transactions.append(self._finalize_tx(current_tx))

        return transactions

    def _finalize_tx(self, tx_data: Dict[str, Any]) -> Dict[str, Any]:
        text_body = tx_data["text_body"].replace('|', ' ').strip()
        text_body = re.sub(r'\s+', ' ', text_body)
        
        tail_pattern = re.compile(r'(?:(\d{6})\s+)?(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)\s+(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?(?:\s*[CD]R)?)$', re.IGNORECASE)
        
        match = tail_pattern.search(text_body)

        cheque_no = ""
        debit = 0.0
        credit = 0.0
        balance = 0.0
        narration = text_body

        if match:
            cheque_no = match.group(1) or ""
            amt_val = self._clean_amount(match.group(2))
            balance = self._clean_amount(match.group(3))
            
            narration = text_body[:match.start()].strip()

            debit_keywords = ["REMT", "DEBIT", "TRANSFER TO", "CASH WITHDRAWAL", "INT TRF", "POS", "SI FAIL", "DIRECT DR", "ACH", "CHQ"]
            
            if any(kw in narration.upper() for kw in debit_keywords) and not ("DEP TFR" in narration.upper() or "RELEASE" in narration.upper() or "CREDIT" in narration.upper()):
                debit = amt_val
            else:
                credit = amt_val
        else:
            chq_m = re.search(r'\b(\d{6})\b', text_body)
            if chq_m:
                cheque_no = chq_m.group(1)
            
            amounts = re.findall(r'(\d{1,3}(?:,\d{2,3})*\.\d+)', text_body)
            if len(amounts) >= 2:
                amt_val = self._clean_amount(amounts[-2])
                balance = self._clean_amount(amounts[-1])
                if "DEP TFR" in text_body or "UPI/CR" in text_body:
                    credit = amt_val
                else:
                    debit = amt_val
            elif len(amounts) == 1:
                credit = self._clean_amount(amounts[0])

        narr_final = narration or text_body
        counter_ledger = "SUSPENS"
        if hasattr(self, 'rules_engine') and self.rules_engine:
            counter_ledger = self.rules_engine.match_ledger(narr_final)

        return {
            "date": tx_data["date"],
            "value_date": tx_data["value_date"],
            "narration": narr_final,
            "cheque_no": cheque_no,
            "debit": debit,
            "credit": credit,
            "balance": balance,
            "counter_ledger": counter_ledger
        }


class CustomColumnBankParser(BaseBankParser):
    """
    Parser that uses explicit user-configured or AI-inferred column mapping dict.
    column_map = {
        "date": int,
        "value_date": int or None,
        "narration": int,
        "cheque_no": int or None,
        "debit": int or None,
        "credit": int or None,
        "balance": int or None
    }
    """
    bank_name = "Custom / AI Mapped Statement"

    def __init__(self, column_map: Dict[str, Optional[int]]):
        self.column_map = column_map

    def parse(self, pdf_path: str, rules_engine: Optional[Any] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        metadata = {"bank_name": "Custom Mapped Statement", "account_no": "", "account_name": ""}
        transactions = []

        if not pdfplumber:
            return metadata, transactions

        cmap = self.column_map
        date_idx = cmap.get("date")
        vdate_idx = cmap.get("value_date")
        narr_idx = cmap.get("narration")
        chq_idx = cmap.get("cheque_no")
        debit_idx = cmap.get("debit")
        credit_idx = cmap.get("credit")
        bal_idx = cmap.get("balance")

        date_pattern = re.compile(r'\b(\d{2}[-/.]\d{2}[-/.]\d{2,4})\b')

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) == 0:
                            continue

                        row_cells = [str(c or "").strip() for c in row]

                        # Verify date
                        if date_idx is None or date_idx >= len(row_cells):
                            row_str = " ".join(row_cells)
                            dt_m = date_pattern.search(row_str)
                            if not dt_m:
                                continue
                            dt = dt_m.group(1)
                        else:
                            dt_val = row_cells[date_idx]
                            dt_m = date_pattern.search(dt_val)
                            if not dt_m:
                                continue
                            dt = dt_m.group(1)

                        val_dt = row_cells[vdate_idx] if vdate_idx is not None and vdate_idx < len(row_cells) else dt
                        desc = row_cells[narr_idx] if narr_idx is not None and narr_idx < len(row_cells) else ""
                        chq = row_cells[chq_idx] if chq_idx is not None and chq_idx < len(row_cells) else ""
                        
                        debit_val = self._clean_amount(row_cells[debit_idx]) if debit_idx is not None and debit_idx < len(row_cells) else 0.0
                        credit_val = self._clean_amount(row_cells[credit_idx]) if credit_idx is not None and credit_idx < len(row_cells) else 0.0
                        bal_val = self._clean_amount(row_cells[bal_idx]) if bal_idx is not None and bal_idx < len(row_cells) else 0.0

                        desc_clean = " ".join(desc.split())
                        counter_ledger = "SUSPENS"
                        if rules_engine:
                            counter_ledger = rules_engine.match_ledger(desc_clean)

                        transactions.append({
                            "date": dt,
                            "value_date": val_dt,
                            "narration": desc_clean,
                            "cheque_no": chq,
                            "debit": debit_val,
                            "credit": credit_val,
                            "balance": bal_val,
                            "counter_ledger": counter_ledger
                        })

        return metadata, transactions


class HDFCBankParser(BaseBankParser):
    """Parser for HDFC Bank Statements."""
    bank_name = "HDFC Bank"

    def parse(self, pdf_path: str, rules_engine: Optional[Any] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        metadata = {"bank_name": "HDFC Bank", "account_no": "", "account_name": ""}
        transactions = []
        if not pdfplumber:
            return metadata, transactions

        date_pattern = re.compile(r'^\d{2}/\d{2}/\d{2,4}$')
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 5:
                            continue
                        dt = (row[0] or "").strip()
                        if not date_pattern.match(dt):
                            continue
                        desc = (row[1] or "").strip()
                        chq = (row[2] or "").strip()
                        val_dt = (row[3] or "").strip()
                        withdrawal = self._clean_amount(row[4])
                        deposit = self._clean_amount(row[5]) if len(row) > 5 else 0.0
                        bal = self._clean_amount(row[6]) if len(row) > 6 else 0.0

                        desc_clean = " ".join(desc.split())
                        counter_ledger = "SUSPENS"
                        if rules_engine:
                            counter_ledger = rules_engine.match_ledger(desc_clean)

                        transactions.append({
                            "date": dt,
                            "value_date": val_dt,
                            "narration": desc_clean,
                            "cheque_no": chq,
                            "debit": withdrawal,
                            "credit": deposit,
                            "balance": bal,
                            "counter_ledger": counter_ledger
                        })
        return metadata, transactions


class GenericBankParser(BaseBankParser):
    """Smart Generic Parser for any Bank Statement layout."""
    bank_name = "Generic Auto-Detect"

    def parse(self, pdf_path: str, rules_engine: Optional[Any] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        metadata = {"bank_name": "Auto-Detected Bank Statement", "account_no": "", "account_name": ""}
        transactions = []
        
        if pdfplumber:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            row_str = " ".join([str(c) for c in row if c])
                            date_match = re.search(r'\b(\d{2}[-/.]\d{2}[-/.]\d{2,4})\b', row_str)
                            if not date_match:
                                continue
                            
                            clean_row = [str(c).strip() for c in row if c is not None]
                            if len(clean_row) < 4:
                                continue

                            dt = date_match.group(1)
                            amounts = [self._clean_amount(c) for c in clean_row if self._clean_amount(c) > 0]
                            
                            debit = 0.0
                            credit = 0.0
                            balance = 0.0

                            if len(amounts) >= 3:
                                debit, credit, balance = amounts[0], amounts[1], amounts[2]
                            elif len(amounts) == 2:
                                balance = amounts[1]
                                if "DR" in row_str.upper() or "DEBIT" in row_str.upper() or "WITHDRAWAL" in row_str.upper():
                                    debit = amounts[0]
                                else:
                                    credit = amounts[0]

                            desc = " ".join([c for c in clean_row if not re.search(r'^\d+([.,]\d+)?$', c)])
                            counter_ledger = "SUSPENS"
                            if rules_engine:
                                counter_ledger = rules_engine.match_ledger(desc)

                            transactions.append({
                                "date": dt,
                                "value_date": dt,
                                "narration": desc,
                                "cheque_no": "",
                                "debit": debit,
                                "credit": credit,
                                "balance": balance,
                                "counter_ledger": counter_ledger
                            })
        return metadata, transactions


def extract_pdf_raw_table_sample(pdf_path: str) -> Tuple[List[str], List[List[str]]]:
    """
    Extracts raw table header strings and first 5 sample data rows from PDF using pdfplumber.
    """
    headers = []
    sample_rows = []

    if not pdfplumber:
        return headers, sample_rows

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        clean_row = [str(c or "").replace('\n', ' ').strip() for c in row if c is not None]
                        if not any(clean_row):
                            continue
                        if not headers:
                            headers = [c if c else f"Column {i+1}" for i, c in enumerate(clean_row)]
                        else:
                            sample_rows.append(clean_row)
                            if len(sample_rows) >= 5:
                                break
                    if len(sample_rows) >= 5:
                        break
                if len(sample_rows) >= 5:
                    break
    except Exception:
        pass

    return headers, sample_rows


def detect_and_parse_pdf(pdf_path: str, rules_engine: Optional[Any] = None, column_map: Optional[Dict[str, Optional[int]]] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if column_map:
        parser = CustomColumnBankParser(column_map)
        return parser.parse(pdf_path, rules_engine=rules_engine)

    text = ""
    if pdfplumber:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) > 0:
                    text = pdf.pages[0].extract_text() or ""
        except Exception:
            pass

    if not text and fitz:
        try:
            doc = fitz.open(pdf_path)
            if len(doc) > 0:
                text = doc[0].get_text("text")
        except Exception:
            pass

    text_upper = text.upper()

    if "STATE BANK OF INDIA" in text_upper or "SBI" in text_upper or "SBIN" in text_upper:
        parser = SBIBankParser()
    elif "HDFC" in text_upper:
        parser = HDFCBankParser()
    else:
        parser = SBIBankParser()

    return parser.parse(pdf_path, rules_engine=rules_engine)
