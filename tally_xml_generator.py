import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import List, Dict, Any, Optional

class TallyXMLGenerator:
    """
    Generates Tally XML compliant with Tally Prime / Tally.ERP 9.
    Translates bank statement transactions into Receipt & Payment Vouchers.
    """
    def __init__(self, company_name: str = "Company Name", bank_ledger: str = "State Bank of India", default_counter_ledger: str = "SUSPENS"):
        self.company_name = company_name
        self.bank_ledger = bank_ledger
        self.default_counter_ledger = default_counter_ledger

    def _format_date(self, dt: Any) -> str:
        """Converts date strings/objects into YYYYMMDD format."""
        if not dt:
            return datetime.now().strftime("%Y%m%d")
        if isinstance(dt, datetime):
            return dt.strftime("%Y%m%d")
        dt_str = str(dt).strip()
        # Common date formats in statements: DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY, etc.
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%Y%m%d"):
            try:
                parsed_dt = datetime.strptime(dt_str, fmt)
                return parsed_dt.strftime("%Y%m%d")
            except ValueError:
                pass
        # Clean any non-digits if already 8 chars
        digits_only = "".join(filter(str.isdigit, dt_str))
        if len(digits_only) == 8:
            return digits_only
        return datetime.now().strftime("%Y%m%d")

    def generate_xml(self, transactions: List[Dict[str, Any]], start_voucher_num: int = 1) -> str:
        envelope = ET.Element("ENVELOPE")
        
        header = ET.SubElement(envelope, "HEADER")
        tally_req = ET.SubElement(header, "TALLYREQUEST")
        tally_req.text = "Import Data"
        
        body = ET.SubElement(envelope, "BODY")
        import_data = ET.SubElement(body, "IMPORTDATA")
        
        req_desc = ET.SubElement(import_data, "REQUESTDESC")
        report_name = ET.SubElement(req_desc, "REPORTNAME")
        report_name.text = "Vouchers"
        static_vars = ET.SubElement(req_desc, "STATICVARIABLES")
        curr_comp = ET.SubElement(static_vars, "SVCURRENTCOMPANY")
        curr_comp.text = self.company_name
        
        req_data = ET.SubElement(import_data, "REQUESTDATA")
        tally_msg = ET.SubElement(req_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        
        v_num = start_voucher_num
        for tx in transactions:
            dt_str = self._format_date(tx.get("date"))
            narration = str(tx.get("narration") or "").strip()
            cheque_no = str(tx.get("cheque_no") or "").strip()
            party_ledger = str(tx.get("counter_ledger") or self.default_counter_ledger).strip()
            
            debit = float(tx.get("debit") or 0)
            credit = float(tx.get("credit") or 0)
            
            if credit > 0:
                vch_type = "Receipt"
                amount = credit
            elif debit > 0:
                vch_type = "Payment"
                amount = debit
            else:
                continue # Skip transactions with no debit or credit
                
            voucher = ET.SubElement(tally_msg, "VOUCHER", {
                "VCHTYPE": vch_type,
                "ACTION": "Create",
                "OBJVIEW": "Accounting Voucher View"
            })
            
            ET.SubElement(voucher, "DATE").text = dt_str
            ET.SubElement(voucher, "VCHSTATUSDATE").text = dt_str
            ET.SubElement(voucher, "NARRATION").text = narration
            ET.SubElement(voucher, "VOUCHERTYPENAME").text = vch_type
            ET.SubElement(voucher, "PARTYLEDGERNAME").text = party_ledger
            ET.SubElement(voucher, "VOUCHERNUMBER").text = str(v_num)
            ET.SubElement(voucher, "PERSISTEDVIEW").text = "Accounting Voucher View"
            ET.SubElement(voucher, "EFFECTIVEDATE").text = dt_str
            
            # Entry 1: Counter/Party Ledger
            entry1 = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(entry1, "LEDGERNAME").text = party_ledger
            if vch_type == "Receipt":
                ET.SubElement(entry1, "ISDEEMEDPOSITIVE").text = "No"
                ET.SubElement(entry1, "AMOUNT").text = f"{amount:.2f}".rstrip('0').rstrip('.')
            else: # Payment
                ET.SubElement(entry1, "ISDEEMEDPOSITIVE").text = "Yes"
                ET.SubElement(entry1, "AMOUNT").text = f"{-amount:.2f}".rstrip('0').rstrip('.')
                
            # Entry 2: Bank Ledger
            entry2 = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(entry2, "LEDGERNAME").text = self.bank_ledger
            if vch_type == "Receipt":
                ET.SubElement(entry2, "ISDEEMEDPOSITIVE").text = "Yes"
                ET.SubElement(entry2, "AMOUNT").text = f"{-amount:.2f}".rstrip('0').rstrip('.')
            else: # Payment
                ET.SubElement(entry2, "ISDEEMEDPOSITIVE").text = "No"
                ET.SubElement(entry2, "AMOUNT").text = f"{amount:.2f}".rstrip('0').rstrip('.')
                
            # Bank Allocations
            bank_alloc = ET.SubElement(entry2, "BANKALLOCATIONS.LIST")
            ET.SubElement(bank_alloc, "DATE").text = dt_str
            ET.SubElement(bank_alloc, "INSTRUMENTDATE").text = dt_str
            ET.SubElement(bank_alloc, "TRANSACTIONTYPE").text = str(tx.get("transaction_type") or "Cheque/DD")
            ET.SubElement(bank_alloc, "PAYMENTFAVOURING").text = party_ledger
            inst_num = ET.SubElement(bank_alloc, "INSTRUMENTNUMBER")
            if cheque_no:
                inst_num.text = cheque_no
            ET.SubElement(bank_alloc, "PAYMENTMODE").text = "Transacted"
            ET.SubElement(bank_alloc, "BANKPARTYNAME").text = party_ledger
            if vch_type == "Receipt":
                ET.SubElement(bank_alloc, "AMOUNT").text = f"{-amount:.2f}".rstrip('0').rstrip('.')
            else:
                ET.SubElement(bank_alloc, "AMOUNT").text = f"{amount:.2f}".rstrip('0').rstrip('.')
                
            v_num += 1

        xml_raw = ET.tostring(envelope, encoding="utf-8")
        parsed = minidom.parseString(xml_raw)
        return parsed.toprettyxml(indent="  ")
