"""
Deterministic eligibility checks used alongside AI evaluation.
"""
import re
from typing import Any, Dict, List, Optional


class RuleEvaluationService:
    """Apply conservative, auditable checks for common tender criteria."""

    MONEY_UNITS = {
        "crore": 10_000_000,
        "cr": 10_000_000,
        "lakh": 100_000,
        "lac": 100_000,
        "inr": 1,
        "rs": 1,
        "rupees": 1,
    }

    @classmethod
    def augment_criteria(cls, ai_criteria: List[Dict[str, Any]], tender_text: str) -> List[Dict[str, Any]]:
        """Add deterministic criteria only when they do not duplicate LLM-extracted criteria."""
        combined = list(ai_criteria or [])
        existing = [set(cls._keywords(item.get("description", ""))) for item in combined]

        for rule_item in cls.extract_basic_criteria(tender_text):
            rule_words = set(cls._keywords(rule_item.get("description", "")))
            if not rule_words:
                continue
            duplicate = any(len(rule_words.intersection(words)) >= max(2, min(len(rule_words), 3)) for words in existing)
            if duplicate:
                continue
            rule_item["criterion_id"] = rule_item.get("criterion_id") or f"RULE_{len(combined) + 1:03d}"
            rule_item["source"] = "rule_extraction"
            combined.append(rule_item)
            existing.append(rule_words)
        return combined

    @classmethod
    def extract_basic_criteria(cls, tender_text: str) -> List[Dict[str, Any]]:
        """Fallback extraction for common eligibility rules when the LLM is unavailable."""
        criteria = []
        patterns = [
            ("financial", r"(turnover[^.\n]{0,160}?(?:>=|not less than|minimum|at least)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(crore|cr|lakh|lac)?)"),
            ("technical", r"((?:similar )?projects?[^.\n]{0,160}?(?:>=|not less than|minimum|at least)\s*(\d+))"),
            ("technical", r"(experience[^.\n]{0,160}?(?:>=|not less than|minimum|at least)\s*(\d+)\s*years?)"),
        ]
        for criterion_type, pattern in patterns:
            for match in re.finditer(pattern, tender_text, re.IGNORECASE):
                unit = match.group(3) if len(match.groups()) >= 3 else None
                criteria.append({
                    "criterion_id": f"RULE_{len(criteria) + 1:03d}",
                    "type": criterion_type,
                    "description": cls._clean_snippet(match.group(1)),
                    "operator": ">=",
                    "value": float(match.group(2)),
                    "unit": unit,
                    "allowed_values": None,
                    "is_mandatory": True,
                    "source_page": cls._page_near(tender_text, match.start()),
                    "source_text": cls._clean_snippet(match.group(0)),
                })

        presence_terms = [
            ("compliance", "GST registration", r"\b(?:GSTIN|GST\s+(?:registration|certificate|number|no\.?))\b[^.\n]{0,120}"),
            ("compliance", "PAN registration", r"\bPAN\s+(?:registration|card|number|no\.?)\b[^.\n]{0,120}"),
            ("compliance", "ISO certification", r"\bISO\b[^.\n]{0,120}(?:9001|certification|certificate)"),
        ]
        for criterion_type, label, pattern in presence_terms:
            match = re.search(pattern, tender_text, re.IGNORECASE)
            if match:
                criteria.append({
                    "criterion_id": f"RULE_{len(criteria) + 1:03d}",
                    "type": criterion_type,
                    "description": cls._clean_snippet(match.group(0)) or label,
                    "operator": None,
                    "value": None,
                    "unit": None,
                    "allowed_values": None,
                    "is_mandatory": True,
                    "source_page": cls._page_near(tender_text, match.start()),
                    "source_text": cls._clean_snippet(match.group(0)),
                })
        return criteria

    @classmethod
    def evaluate(
        cls,
        tender_criteria: List[Dict[str, Any]],
        bidder_text: str,
        documents: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        document_blocks = cls._document_blocks(documents, bidder_text)
        results = []

        for criterion in tender_criteria:
            description = criterion.get("criterion") or criterion.get("description") or "Tender criterion"
            operator = criterion.get("operator")
            value = criterion.get("value")
            unit = criterion.get("unit")
            allowed_values = criterion.get("allowed_values")
            mandatory = bool(criterion.get("mandatory", criterion.get("is_mandatory", True)))

            numeric_result = cls._evaluate_numeric(description, operator, value, unit, document_blocks)
            if numeric_result:
                numeric_result["criterion"] = description
                numeric_result["mandatory"] = mandatory
                results.append(numeric_result)
                continue

            choice_result = cls._evaluate_allowed_values(description, allowed_values, document_blocks, mandatory)
            if choice_result:
                choice_result["criterion"] = description
                choice_result["mandatory"] = mandatory
                results.append(choice_result)
                continue

            compliance_result = cls._evaluate_presence(description, document_blocks, mandatory)
            if compliance_result:
                compliance_result["criterion"] = description
                compliance_result["mandatory"] = mandatory
                results.append(compliance_result)

        return results

    @classmethod
    def merge_with_ai(
        cls,
        ai_data: Dict[str, Any],
        rule_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ai_results = ai_data.get("criteria_results") or []
        merged = []
        used_rule_indexes = set()

        for ai_item in ai_results:
            matched_index = cls._best_rule_match(ai_item.get("criterion", ""), rule_results, used_rule_indexes)
            if matched_index is None:
                merged.append(ai_item)
                continue

            rule_item = rule_results[matched_index]
            used_rule_indexes.add(matched_index)
            merged.append(cls._merge_item(ai_item, rule_item))

        for index, rule_item in enumerate(rule_results):
            if index not in used_rule_indexes:
                merged.append(rule_item)

        has_fail = any(item.get("decision") == "FAIL" and item.get("mandatory", True) for item in merged)
        has_review = any(item.get("decision") == "NEEDS_REVIEW" and item.get("mandatory", True) for item in merged)
        if has_fail:
            decision = "not_eligible"
        elif has_review:
            decision = "needs_manual_review"
        else:
            decision = "eligible"

        confidences = [float(item.get("confidence") or 0.0) for item in merged]
        ai_data["criteria_results"] = merged
        ai_data["overall_decision"] = decision
        ai_data["overall_confidence"] = (sum(confidences) / len(confidences)) if confidences else float(ai_data.get("overall_confidence") or 0.0)
        ai_data["evaluation_method"] = "hybrid"
        if merged:
            fail_count = sum(1 for item in merged if item.get("decision") == "FAIL")
            review_count = sum(1 for item in merged if item.get("decision") == "NEEDS_REVIEW")
            ai_data["decision_summary"] = (
                f"Hybrid evaluation completed across {len(merged)} criteria. "
                f"{fail_count} failed and {review_count} require manual review."
            )
        return ai_data

    @classmethod
    def _evaluate_numeric(
        cls,
        description: str,
        operator: Optional[str],
        required_value: Optional[float],
        required_unit: Optional[str],
        document_blocks: List[Dict[str, str]],
    ) -> Optional[Dict[str, Any]]:
        if required_value is None or not operator:
            return None
        if not required_unit and not any(term in description.lower() for term in ["turnover", "net worth", "networth", "revenue", "project", "experience", "year", "staff", "employee", "quantity", "capacity", "percentage", "%"]):
            return None

        keywords = cls._keywords(description)
        evidence = cls._find_numeric_evidence(document_blocks, keywords, required_unit, description)
        if not evidence:
            return cls._review("Numeric evidence was not found in bidder documents.")

        required = cls._normalize_number(float(required_value), required_unit)
        actual = cls._normalize_number(evidence["value"], evidence.get("unit"))
        if required is None or actual is None:
            return cls._review("Numeric value was found, but its unit could not be normalized.", evidence)

        passed = cls._compare(actual, operator, required)
        decision = "PASS" if passed else "FAIL"
        return {
            "extracted_value": evidence["raw"],
            "source_document": evidence["source_document"],
            "source_page": evidence.get("source_page"),
            "evidence_snippet": evidence["snippet"],
            "decision": decision,
            "confidence": 0.9,
            "reasoning": (
                f"Required {operator} {required_value} {required_unit or ''}; "
                f"found {evidence['raw']} in bidder evidence."
            ),
        }

    @classmethod
    def _evaluate_presence(
        cls,
        description: str,
        document_blocks: List[Dict[str, str]],
        mandatory: bool,
    ) -> Optional[Dict[str, Any]]:
        lowered = description.lower()
        targets = []
        if "gst" in lowered:
            evidence = cls._find_identifier_evidence(document_blocks, "gst")
            if evidence:
                return {
                    "extracted_value": evidence["matched"],
                    "source_document": evidence["source_document"],
                    "source_page": evidence.get("source_page"),
                    "evidence_snippet": evidence["snippet"],
                    "decision": "PASS",
                    "confidence": 0.9,
                    "reasoning": "GSTIN evidence appears in bidder documents. Procurement officer should confirm registration validity where applicable.",
                }
            targets = [r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", "gst"]
        elif "pan" in lowered:
            evidence = cls._find_identifier_evidence(document_blocks, "pan")
            if evidence:
                return {
                    "extracted_value": evidence["matched"],
                    "source_document": evidence["source_document"],
                    "source_page": evidence.get("source_page"),
                    "evidence_snippet": evidence["snippet"],
                    "decision": "PASS",
                    "confidence": 0.9,
                    "reasoning": "PAN evidence appears in bidder documents. Procurement officer should confirm document validity where applicable.",
                }
            targets = [r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "pan"]
        elif "iso" in lowered:
            targets = ["iso", "9001"]
        elif "registration" in lowered:
            targets = ["registration", "registered"]
        elif "project" in lowered or "experience" in lowered:
            targets = ["project", "experience", "work order", "completion"]

        if not targets:
            return None

        evidence = cls._find_text_evidence(document_blocks, targets)
        if evidence:
            return {
                "extracted_value": evidence["matched"],
                "source_document": evidence["source_document"],
                "source_page": evidence.get("source_page"),
                "evidence_snippet": evidence["snippet"],
                "decision": "PASS",
                "confidence": 0.78,
                "reasoning": "Required evidence appears in bidder documents. Procurement officer should confirm validity dates where applicable.",
            }

        return cls._review("Mandatory supporting evidence was not found." if mandatory else "Optional evidence was not found.")

    @classmethod
    def _find_identifier_evidence(cls, blocks: List[Dict[str, str]], identifier: str) -> Optional[Dict[str, Any]]:
        """Find GST/PAN even when OCR inserts spaces or punctuation between characters."""
        if identifier == "gst":
            label_pattern = re.compile(r"\bGST(?:IN|I?N|[\s.-]*(?:no|number|registration))?\b", re.IGNORECASE)
            normalized_pattern = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
        elif identifier == "pan":
            label_pattern = re.compile(r"\bPAN(?:[\s.-]*(?:no|number|card))?\b", re.IGNORECASE)
            normalized_pattern = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
        else:
            return None

        for block in blocks:
            text = block["text"] or ""

            # Prefer identifier values near labels to avoid treating unrelated IDs as compliance evidence.
            for label_match in label_pattern.finditer(text):
                window_start = max(0, label_match.start() - 40)
                window_end = min(len(text), label_match.end() + 220)
                window = text[window_start:window_end]
                value_window = text[label_match.start():window_end]
                normalized = cls._normalize_evidence_token(value_window)
                match = normalized_pattern.search(normalized)
                if match:
                    return {
                        "matched": match.group(0),
                        "source_document": block["source_document"],
                        "source_page": cls._page_near(text, label_match.start()),
                        "snippet": cls._clean_snippet(window),
                    }

            # Fall back to strict normalized full-text search for GSTIN only. PAN is
            # short enough that OCR-combined text can mimic it accidentally.
            if identifier == "pan":
                continue
            normalized_text = cls._normalize_evidence_token(text)
            match = normalized_pattern.search(normalized_text)
            if match:
                start, end = cls._best_identifier_window(text, match.group(0))
                return {
                    "matched": match.group(0),
                    "source_document": block["source_document"],
                    "source_page": cls._page_near(text, start),
                    "snippet": cls._clean_snippet(text[max(0, start - 180): min(len(text), end + 180)]),
                }

        return None

    @classmethod
    def _evaluate_allowed_values(
        cls,
        description: str,
        allowed_values: Optional[List[str]],
        document_blocks: List[Dict[str, str]],
        mandatory: bool,
    ) -> Optional[Dict[str, Any]]:
        if not allowed_values:
            return None

        searchable = " ".join([description, *[str(value) for value in allowed_values]]).lower()
        if "gst" in searchable:
            evidence = cls._find_identifier_evidence(document_blocks, "gst")
            if evidence:
                return {
                    "extracted_value": evidence["matched"],
                    "source_document": evidence["source_document"],
                    "source_page": evidence.get("source_page"),
                    "evidence_snippet": evidence["snippet"],
                    "decision": "PASS",
                    "confidence": 0.9,
                    "reasoning": "GSTIN evidence appears in bidder documents.",
                }
        if "pan" in searchable:
            evidence = cls._find_identifier_evidence(document_blocks, "pan")
            if evidence:
                return {
                    "extracted_value": evidence["matched"],
                    "source_document": evidence["source_document"],
                    "source_page": evidence.get("source_page"),
                    "evidence_snippet": evidence["snippet"],
                    "decision": "PASS",
                    "confidence": 0.9,
                    "reasoning": "PAN evidence appears in bidder documents.",
                }
        if "iso" in searchable:
            evidence = cls._find_text_evidence(document_blocks, ["ISO", "9001"])
            if evidence:
                return {
                    "extracted_value": evidence["matched"],
                    "source_document": evidence["source_document"],
                    "source_page": evidence.get("source_page"),
                    "evidence_snippet": evidence["snippet"],
                    "decision": "PASS",
                    "confidence": 0.82,
                    "reasoning": "ISO-related certification evidence appears in bidder documents. Procurement officer should confirm certificate scope and validity dates.",
                }

        targets = [str(value) for value in allowed_values if str(value).strip()]
        evidence = cls._find_text_evidence(document_blocks, targets)
        if evidence:
            return {
                "extracted_value": evidence["matched"],
                "source_document": evidence["source_document"],
                "source_page": evidence.get("source_page"),
                "evidence_snippet": evidence["snippet"],
                "decision": "PASS",
                "confidence": 0.82,
                "reasoning": f"One allowed value for this criterion appears in bidder evidence: {evidence['matched']}.",
            }

        return cls._review(
            "None of the allowed values were found in bidder documents." if mandatory else "Optional allowed value evidence was not found."
        )

    @staticmethod
    def _document_blocks(documents: Optional[List[Any]], bidder_text: str) -> List[Dict[str, str]]:
        if not documents:
            return [{"source_document": "bidder submission", "text": bidder_text or ""}]
        blocks = []
        for doc in documents:
            blocks.append({
                "source_document": getattr(doc, "file_name", None) or getattr(doc, "document_type", None) or "bidder document",
                "text": getattr(doc, "extracted_text", None) or "",
            })
        return blocks

    @staticmethod
    def _keywords(description: str) -> List[str]:
        useful = []
        for word in re.findall(r"[A-Za-z0-9]{3,}", description.lower()):
            if word not in {"shall", "must", "have", "with", "from", "last", "years", "minimum", "required", "bidder", "bidders"}:
                useful.append(word)
        return useful[:6]

    @classmethod
    def _find_numeric_evidence(
        cls,
        blocks: List[Dict[str, str]],
        keywords: List[str],
        required_unit: Optional[str] = None,
        description: str = "",
    ) -> Optional[Dict[str, Any]]:
        unit = (required_unit or "").lower()
        if unit in {"project", "projects"} or "project" in description.lower():
            evidence = cls._find_labeled_count_evidence(
                blocks,
                [
                    "completed government projects",
                    "completed projects",
                    "government projects",
                    "similar projects",
                    "smart city projects",
                    "smart-city utility projects",
                ],
                "projects",
                keywords,
                description,
            )
            if evidence:
                return evidence
            evidence = cls._find_count_evidence(
                blocks,
                keywords,
                [
                    r"(?P<raw>(?:completed\s+)?(?:government|similar|smart[-\s]?city|utility|infrastructure)?\s*projects?\s*[:\-]\s*(?P<value>\d{1,3})\+?)",
                    r"(?P<raw>(?P<value>\d{1,3})\+?\s*(?:government|similar|smart[-\s]?city|utility|infrastructure)?\s+projects?)",
                    r"(?P<raw>(?:completed|executed|delivered|undertaken)\s+(?P<value>\d{1,3})\+?\s+(?:[A-Za-z-]+\s+){0,5}projects?)",
                    r"(?P<raw>(?P<value>\d{1,3})\+?\s+(?:completed|executed|delivered)\s+projects?)",
                    r"(?P<raw>(?P<value>\d{1,3})\+?\s+(?:successfully\s+)?(?:completed|executed|delivered|undertaken)\s+(?:[A-Za-z-]+\s+){0,5}projects?)",
                ],
                description,
            )
            if evidence:
                evidence["unit"] = "projects"
            return evidence

        if unit in {"year", "years"} or "experience" in description.lower():
            evidence = cls._find_labeled_count_evidence(
                blocks,
                ["years of operation", "years of experience", "operating period"],
                "years",
                keywords,
                description,
            )
            if evidence:
                return evidence
            evidence = cls._find_count_evidence(
                blocks,
                keywords,
                [
                    r"(?P<raw>(?:years?\s+of\s+(?:operation|experience)|operating\s+period)\s*[:\-]\s*(?P<value>\d{1,2})\+?\s*years?)",
                    r"(?P<raw>(?P<value>\d{1,2})\+?\s*years?\s+(?:of\s+)?(?:experience|operation))",
                    r"(?P<raw>(?:experience|operating|operation)[^.\n]{0,80}?(?P<value>\d{1,2})\+?\s*years?)",
                ],
                description,
            )
            if evidence:
                evidence["unit"] = "years"
            return evidence

        money_pattern = re.compile(
            r"(?P<raw>(?:rs\.?|inr|₹)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>crore|cr|lakh|lac|lakhs|inr|rs|rupees)?)",
            re.IGNORECASE,
        )
        for block in blocks:
            text = block["text"]
            for match in money_pattern.finditer(text):
                start, end = match.span()
                window = text[max(0, start - 180): min(len(text), end + 180)]
                if cls._looks_like_address_or_identifier(window, match.group("raw")):
                    continue
                if keywords and not cls._has_relevant_keyword_window(window, keywords, description):
                    continue
                return {
                    "raw": match.group("raw").strip(),
                    "value": float(match.group("value")),
                    "unit": (match.group("unit") or "").lower(),
                    "source_document": block["source_document"],
                    "source_page": cls._page_near(text, start),
                    "snippet": cls._clean_snippet(window),
                }
        return None

    @classmethod
    def _find_count_evidence(
        cls,
        blocks: List[Dict[str, str]],
        keywords: List[str],
        patterns: List[str],
        description: str = "",
    ) -> Optional[Dict[str, Any]]:
        compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        for block in blocks:
            text = block["text"]
            for pattern in compiled:
                for match in pattern.finditer(text):
                    start, end = match.span()
                    window = text[max(0, start - 180): min(len(text), end + 180)]
                    if cls._looks_like_address_or_identifier(window, match.group("raw")):
                        continue
                    if keywords and not cls._has_relevant_keyword_window(window, keywords, description):
                        continue
                    return {
                        "raw": match.group("raw").strip(),
                        "value": float(match.group("value")),
                        "unit": "",
                        "source_document": block["source_document"],
                        "source_page": cls._page_near(text, start),
                        "snippet": cls._clean_snippet(window),
                    }
        return None

    @classmethod
    def _find_labeled_count_evidence(
        cls,
        blocks: List[Dict[str, str]],
        labels: List[str],
        unit: str,
        keywords: List[str],
        description: str,
    ) -> Optional[Dict[str, Any]]:
        for block in blocks:
            text = block["text"] or ""
            normalized = re.sub(r"\s+", " ", text)
            for label in labels:
                label_pattern = r"\s+".join(re.escape(part) for part in label.split())
                pattern = re.compile(
                    rf"(?P<raw>{label_pattern}\s*[:\-]?\s*(?P<value>\d{{1,3}})\+?\s*(?:{re.escape(unit)})?)",
                    re.IGNORECASE,
                )
                match = pattern.search(normalized)
                if not match:
                    continue
                raw = match.group("raw").strip()
                value = float(match.group("value"))
                label_start = text.lower().find(label.split()[0].lower())
                if label_start < 0:
                    label_start = 0
                window = text[max(0, label_start - 180): min(len(text), label_start + 320)]
                if keywords and not cls._has_relevant_keyword_window(f"{window} {raw}", keywords, description):
                    continue
                return {
                    "raw": raw,
                    "value": value,
                    "unit": unit,
                    "source_document": block["source_document"],
                    "source_page": cls._page_near(text, label_start),
                    "snippet": cls._clean_snippet(window),
                }
        return None

    @staticmethod
    def _has_relevant_keyword_window(window: str, keywords: List[str], description: str) -> bool:
        lowered = window.lower()
        if any(keyword in lowered for keyword in keywords):
            return True
        desc = description.lower()
        if "project" in desc:
            return any(term in lowered for term in [
                "completed government projects",
                "completed projects",
                "government projects",
                "smart city",
                "utility infrastructure",
                "major clients",
            ])
        if "year" in desc or "experience" in desc or "operating" in desc:
            return any(term in lowered for term in ["years of operation", "years of experience", "established"])
        if "turnover" in desc:
            return any(term in lowered for term in ["turnover", "annual turnover", "financial"])
        return False

    @staticmethod
    def _looks_like_address_or_identifier(window: str, raw: str) -> bool:
        lowered = window.lower()
        raw_text = raw.strip()
        if raw_text.startswith("#"):
            return True
        if re.fullmatch(r"0+\d{1,3}", raw_text):
            return True
        if re.search(r"-{5,}", window):
            return True
        address_terms = ["office", "road", "street", "pin", "pincode", "bengaluru", "address", "5600", "phone", "mobile"]
        if any(term in lowered for term in address_terms) and not any(term in lowered for term in ["completed", "executed", "delivered", "projects", "experience", "turnover"]):
            return True
        return False

    @classmethod
    def _find_text_evidence(cls, blocks: List[Dict[str, str]], targets: List[str]) -> Optional[Dict[str, Any]]:
        for block in blocks:
            text = block["text"]
            for target in targets:
                flags = re.IGNORECASE
                match = re.search(target, text, flags) if target.startswith("\\") else re.search(re.escape(target), text, flags)
                if match:
                    start, end = match.span()
                    return {
                        "matched": match.group(0),
                        "source_document": block["source_document"],
                        "source_page": cls._page_near(text, start),
                        "snippet": cls._clean_snippet(text[max(0, start - 180): min(len(text), end + 180)]),
                    }
                normalized_target = cls._normalize_evidence_token(target)
                normalized_text = cls._normalize_evidence_token(text)
                if normalized_target and normalized_target in normalized_text:
                    loose_match = re.search(
                        re.escape(target).replace(r"\ ", r"[\s\-_:]*").replace(r"\-", r"[\s\-_:]*"),
                        text,
                        flags,
                    )
                    if loose_match:
                        start, end = loose_match.span()
                    else:
                        start, end = cls._best_token_window(text, target)
                    return {
                        "matched": target,
                        "source_document": block["source_document"],
                        "source_page": cls._page_near(text, start),
                        "snippet": cls._clean_snippet(text[max(0, start - 180): min(len(text), end + 180)]),
                    }
        return None

    @staticmethod
    def _normalize_evidence_token(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value).upper())

    @staticmethod
    def _best_token_window(text: str, target: str) -> tuple[int, int]:
        words = [word for word in re.findall(r"[A-Za-z0-9]+", target) if len(word) >= 3]
        for word in words:
            match = re.search(re.escape(word), text, re.IGNORECASE)
            if match:
                return match.span()
        return 0, min(len(text), 240)

    @staticmethod
    def _best_identifier_window(text: str, normalized_identifier: str) -> tuple[int, int]:
        token = re.escape(normalized_identifier)
        loose_pattern = r"[\s\-_:./]*".join(token)
        match = re.search(loose_pattern, text, re.IGNORECASE)
        if match:
            return match.span()

        compact = RuleEvaluationService._normalize_evidence_token(text)
        compact_index = compact.find(normalized_identifier)
        if compact_index < 0:
            return 0, min(len(text), 240)

        seen = 0
        start = 0
        end = min(len(text), 240)
        for index, char in enumerate(text):
            if re.match(r"[A-Za-z0-9]", char):
                if seen == compact_index:
                    start = index
                seen += 1
                if seen == compact_index + len(normalized_identifier):
                    end = index + 1
                    break
        return start, end

    @classmethod
    def _normalize_number(cls, value: float, unit: Optional[str]) -> Optional[float]:
        normalized_unit = (unit or "inr").lower().strip().rstrip("s")
        if normalized_unit in {"", "number", "project", "projects", "year", "years"}:
            return value
        multiplier = cls.MONEY_UNITS.get(normalized_unit)
        if multiplier is None:
            return None
        return value * multiplier

    @staticmethod
    def _compare(actual: float, operator: str, required: float) -> bool:
        return {
            ">=": actual >= required,
            ">": actual > required,
            "<=": actual <= required,
            "<": actual < required,
            "==": actual == required,
            "=": actual == required,
        }.get(operator, False)

    @staticmethod
    def _page_near(text: str, index: int) -> Optional[int]:
        pages = list(re.finditer(r"\[PAGE\s+(\d+)(?:\s+OCR)?\]", text[:index], re.IGNORECASE))
        if not pages:
            return None
        return int(pages[-1].group(1))

    @staticmethod
    def _clean_snippet(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()[:700]

    @staticmethod
    def _review(reason: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        evidence = evidence or {}
        return {
            "extracted_value": evidence.get("raw"),
            "source_document": evidence.get("source_document"),
            "source_page": evidence.get("source_page"),
            "evidence_snippet": evidence.get("snippet"),
            "decision": "NEEDS_REVIEW",
            "confidence": 0.45,
            "reasoning": reason,
        }

    @staticmethod
    def _best_rule_match(criterion: str, rule_results: List[Dict[str, Any]], used: set) -> Optional[int]:
        criterion_words = set(RuleEvaluationService._keywords(criterion))
        best_index = None
        best_score = 0
        for index, item in enumerate(rule_results):
            if index in used:
                continue
            item_words = set(RuleEvaluationService._keywords(item.get("criterion", "")))
            if criterion_words.intersection(item_words).intersection({"gst", "pan", "iso", "msme", "epf", "esi", "esic"}):
                return index
            score = len(criterion_words.intersection(item_words))
            if score > best_score:
                best_score = score
                best_index = index
        return best_index if best_score else None

    @staticmethod
    def _merge_item(ai_item: Dict[str, Any], rule_item: Dict[str, Any]) -> Dict[str, Any]:
        ai_decision = str(ai_item.get("decision") or "NEEDS_REVIEW").upper()
        rule_decision = str(rule_item.get("decision") or "NEEDS_REVIEW").upper()
        if rule_decision in {"FAIL", "NEEDS_REVIEW"}:
            if ai_decision == "PASS" and (ai_item.get("extracted_value") or ai_item.get("evidence_snippet")):
                base = {**ai_item}
                for key in ("source_document", "source_page", "evidence_snippet", "extracted_value"):
                    base[key] = base.get(key) or rule_item.get(key)
                base["confidence"] = min(float(base.get("confidence") or 0.0), 0.82)
                base["reasoning"] = (
                    f"{ai_item.get('reasoning', 'AI found supporting evidence.')} "
                    f"Deterministic rule check did not override this because it could not confirm the same evidence: "
                    f"{rule_item.get('reasoning')}"
                )
                return base
            if ai_decision == "FAIL" and rule_decision == "NEEDS_REVIEW":
                base = {**ai_item}
                base["confidence"] = min(float(base.get("confidence") or 0.0), 0.78)
                base["reasoning"] = (
                    f"{ai_item.get('reasoning', 'AI marked fail.')} "
                    f"Rule check could not independently confirm failure: {rule_item.get('reasoning')}"
                )
                return base
            base = {**ai_item, **rule_item}
            for key in ("extracted_value", "source_document", "source_page", "evidence_snippet"):
                if not base.get(key) and ai_item.get(key):
                    base[key] = ai_item.get(key)
            base["reasoning"] = f"{rule_item.get('reasoning')} AI note: {ai_item.get('reasoning', 'No AI note.')}"
            return base
        if rule_decision == "PASS" and ai_decision == "PASS":
            base = {**ai_item}
            for key in ("source_document", "source_page", "evidence_snippet", "extracted_value"):
                base[key] = rule_item.get(key) or base.get(key)
            base["confidence"] = max(float(ai_item.get("confidence") or 0), min(float(rule_item.get("confidence") or 0), 0.9))
            base["reasoning"] = f"{ai_item.get('reasoning', 'AI marked pass.')} Deterministic check also found: {rule_item.get('reasoning')}"
            return base
        base = {**ai_item}
        for key in ("source_document", "source_page", "evidence_snippet", "extracted_value"):
            base[key] = rule_item.get(key) or base.get(key)
        base["reasoning"] = (
            f"{ai_item.get('reasoning', 'AI did not mark this as pass.')} "
            f"Deterministic evidence found for manual review context: {rule_item.get('reasoning')}"
        )
        return base
