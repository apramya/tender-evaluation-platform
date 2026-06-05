"""
AI Evaluation Service using Groq's OpenAI-compatible API
"""
import logging
import json
import re
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.utils.config import settings
from app.schemas.schemas import CriterionEvaluation

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL)


class AIEvaluationService:
    """Service for AI-based bidder evaluation"""

    @staticmethod
    async def _chat_text(prompt: str, max_tokens: int = 1000) -> str:
        logger.info("Calling Groq model %s with max_tokens=%s", settings.GROQ_MODEL, max_tokens)
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            top_p=1,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    @staticmethod
    async def _chat_json(prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        content = await AIEvaluationService._chat_text(prompt, max_tokens=max_tokens)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(content[start:end + 1])
            raise
    
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def extract_criteria_from_tender(tender_text: str) -> Dict[str, Any]:
        """
        Use AI to extract eligibility criteria from tender document
        """
        chunks = AIEvaluationService._text_chunks(tender_text, size=18000, overlap=1200)
        all_criteria: List[Dict[str, Any]] = []
        failed_sections = 0

        for chunk_index, chunk in enumerate(chunks, start=1):
            prompt = f"""
        Analyze this tender document and extract the bidder eligibility/evaluation criteria that are actually
        stated in the uploaded tender. Be domain-neutral: this may be civil works,
        IT/software, medical supplies, consultancy, manpower, transport, facilities, equipment, education,
        or any other procurement category.
        Return a JSON object with the following structure:
        {{
            "criteria": [
                {{
                    "criterion_id": "FIN_001",
                    "type": "financial|technical|compliance|mandatory|optional",
                    "value_kind": "money|count|years|percentage|date|text|presence|certification|license|legal|other",
                    "description": "...",
                    "operator": ">=|<=|==|>|<|in",
                    "value": null or numeric value,
                    "unit": "crore|percentage|etc",
                    "allowed_values": null or ["value1", "value2"],
                    "is_mandatory": true|false,
                    "source_page": page number if available,
                    "source_text": "short source clause"
                }}
            ]
        }}

        Rules:
        - Extract only criteria that determine bidder eligibility, qualification, compliance, technical capability, financial capability, legal eligibility, or scoring/evaluation.
        - Do not summarize several independent requirements into one criterion. Split combined clauses into separate atomic criteria.
        - Extract documentary compliance requirements when the tender says a bidder must submit/furnish/provide them, including bid security, tender fee receipt, power of attorney, certificates, registrations, declarations, undertakings, financial statements, technical documents, and experience proof.
        - Extract every explicit certificate, registration, license, financial threshold, experience threshold, technical capability, legal condition, and disqualification condition only when it affects bidder eligibility/evaluation.
        - Do not extract purely administrative items such as contact details, cover letter, table of contents, page numbering, file format, index, signature location, portal URLs, bid opening dates, office addresses, or upload instructions unless the clause says the bidder must submit a compliance document.
        - Do not add inferred/common procurement criteria that are not stated in this tender section.
        - If a clause has multiple alternatives, keep the alternatives in one criterion only when the tender says any one alternative is acceptable.
        - Do not extract general scope of work, payment terms, addresses, page numbers, bid dates, or contact details as eligibility criteria unless explicitly required for bidder qualification.
        - Treat shall/must/required/eligible only if as mandatory.
        - Treat may/preferably/desirable as optional unless the clause says rejection/disqualification.
        - Preserve legal ambiguity in the description instead of simplifying it away.
        - This is section {chunk_index} of {len(chunks)}. Extract all criteria visible in this section, even if similar criteria may appear elsewhere.
        
        Tender Document Section:
        {chunk}
        
        Return ONLY valid JSON, no other text.
        """

            try:
                try:
                    criteria_data = await AIEvaluationService._chat_json(prompt, max_tokens=5000)
                    all_criteria.extend(criteria_data.get("criteria", []) or [])
                except json.JSONDecodeError:
                    logger.error("Failed to parse AI criteria response as JSON for section %s", chunk_index)
            except Exception as e:
                logger.warning(
                    "AI criteria extraction failed for section %s; deterministic fallback will continue: %s",
                    chunk_index,
                    e,
                )
                failed_sections += 1
                continue

        deterministic = AIEvaluationService.extract_rule_based_tender_criteria(tender_text)
        llm_deduped = AIEvaluationService._filter_extracted_criteria(
            AIEvaluationService._dedupe_criteria(all_criteria)
        )
        deterministic_deduped = AIEvaluationService._filter_extracted_criteria(
            AIEvaluationService._dedupe_criteria(deterministic)
        )
        # When the LLM returns a structured checklist, keep that as the source
        # of truth for criterion count. Broad deterministic clause extraction is
        # still used later for evidence checks, but should not inflate an 8-item
        # tender checklist into many repeated compliance rows.
        deduped = llm_deduped if llm_deduped else deterministic_deduped
        logger.info(
            "Extracted %s criteria from tender across %s section(s): llm_raw=%s llm_used=%s deterministic_raw=%s deterministic_used=%s failed_sections=%s",
            len(deduped),
            len(chunks),
            len(all_criteria),
            len(llm_deduped),
            len(deterministic),
            0 if llm_deduped else len(deterministic_deduped),
            failed_sections,
        )
        return {
            "criteria": deduped,
            "metadata": {
                "llm_raw_criteria_count": len(all_criteria),
                "llm_used_criteria_count": len(llm_deduped),
                "deterministic_raw_criteria_count": len(deterministic),
                "deterministic_used_criteria_count": 0 if llm_deduped else len(deterministic_deduped),
                "failed_sections": failed_sections,
                "section_count": len(chunks),
            },
        }

    @staticmethod
    def _text_chunks(text: str, size: int, overlap: int) -> List[str]:
        if not text:
            return [""]
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start:start + size])
            if start + size >= len(text):
                break
            start = max(start + size - overlap, start + 1)
        return chunks

    @staticmethod
    def _dedupe_criteria(criteria: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen_words: List[set] = []
        seen_keys: set = set()
        for item in criteria:
            description = item.get("description") or item.get("criterion") or ""
            key = AIEvaluationService._criterion_key(description)
            if key and (key in seen_keys or AIEvaluationService._is_contained_duplicate_key(key, seen_keys)):
                continue
            words = set(AIEvaluationService._criterion_keywords(description))
            if words and any(AIEvaluationService._looks_like_same_criterion(words, existing) for existing in seen_words):
                continue
            if not item.get("criterion_id"):
                item["criterion_id"] = f"AI_{len(deduped) + 1:03d}"
            deduped.append(item)
            if key:
                seen_keys.add(key)
            seen_words.append(words)
        return deduped

    @staticmethod
    def _is_contained_duplicate_key(key: str, seen_keys: set) -> bool:
        if key.startswith("identifier:"):
            return key in seen_keys
        if len(key) < 24:
            return False
        for existing in seen_keys:
            if existing.startswith("identifier:"):
                continue
            if key in existing or existing in key:
                return True
        return False

    @staticmethod
    def _filter_extracted_criteria(criteria: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove generic bid-submission/admin items that are not evaluation criteria."""
        filtered = []
        for item in criteria:
            description = item.get("description") or item.get("criterion") or ""
            if AIEvaluationService._is_administrative_submission_item(description):
                continue
            filtered.append(item)
        return filtered

    @staticmethod
    def extract_rule_based_tender_criteria(tender_text: str) -> List[Dict[str, Any]]:
        """Conservative fallback that extracts explicit tender clauses missed by the LLM."""
        criteria: List[Dict[str, Any]] = []
        seen = set()
        cleaned_text = re.sub(r"\s+", " ", tender_text or "")
        for description, source in AIEvaluationService._extract_numbered_criteria(tender_text or ""):
            if AIEvaluationService._is_administrative_submission_item(description):
                continue
            key = AIEvaluationService._criterion_key(description)
            if not key or key in seen:
                continue
            seen.add(key)
            criteria.append({
                "criterion_id": f"RB_{len(criteria) + 1:03d}",
                "type": AIEvaluationService._infer_criterion_type(description),
                "value_kind": "presence",
                "description": description,
                "operator": AIEvaluationService._infer_operator(description),
                "value": AIEvaluationService._infer_numeric_value(description),
                "unit": AIEvaluationService._infer_unit(description),
                "allowed_values": None,
                "is_mandatory": AIEvaluationService._is_mandatory_clause(description),
                "source_page": AIEvaluationService._page_near(tender_text, source),
                "source_text": source[:700],
            })

        clauses = re.split(r"(?<=[.;:])\s+", cleaned_text)

        for clause in clauses:
            clause = AIEvaluationService._clean_source_clause(clause)
            if len(clause) < 18:
                continue
            if AIEvaluationService._is_administrative_submission_item(clause):
                continue
            if not AIEvaluationService._looks_like_tender_criterion_clause(clause):
                continue

            for description in AIEvaluationService._split_documentary_clause(clause):
                key = AIEvaluationService._criterion_key(description)
                if not key or key in seen:
                    continue
                seen.add(key)
                criteria.append({
                    "criterion_id": f"RB_{len(criteria) + 1:03d}",
                    "type": AIEvaluationService._infer_criterion_type(description),
                    "value_kind": "presence",
                    "description": description,
                    "operator": None,
                    "value": None,
                    "unit": None,
                    "allowed_values": None,
                    "is_mandatory": AIEvaluationService._is_mandatory_clause(description),
                    "source_page": AIEvaluationService._page_near(tender_text, clause),
                    "source_text": clause[:700],
                })

        threshold_patterns = [
            (
                "financial",
                r"(?P<clause>[^.\n]{0,180}(?:turnover|net worth|solvency)[^.\n]{0,120}(?:minimum|at least|not less than|>=|greater than)\s*(?:rs\.?|inr|₹)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>crore|cr|lakh|lac|lakhs)?)",
            ),
            (
                "technical",
                r"(?P<clause>[^.\n]{0,180}(?:completed|executed|similar|eligible|experience|projects?)[^.\n]{0,160}(?:minimum|at least|not less than|>=|greater than)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>years?|projects?)?)",
            ),
        ]
        for criterion_type, pattern in threshold_patterns:
            for match in re.finditer(pattern, cleaned_text, re.IGNORECASE):
                description = AIEvaluationService._clean_source_clause(match.group("clause"))
                if not description or AIEvaluationService._is_administrative_submission_item(description):
                    continue
                key = AIEvaluationService._criterion_key(description)
                if key in seen:
                    continue
                seen.add(key)
                criteria.append({
                    "criterion_id": f"RB_{len(criteria) + 1:03d}",
                    "type": criterion_type,
                    "value_kind": "money" if criterion_type == "financial" else "count",
                    "description": description,
                    "operator": ">=",
                    "value": float(match.group("value")),
                    "unit": (match.group("unit") or "").strip() or None,
                    "allowed_values": None,
                    "is_mandatory": True,
                    "source_page": AIEvaluationService._page_near(tender_text, match.group("clause")),
                    "source_text": description[:700],
                })

        return criteria

    @staticmethod
    def _extract_numbered_criteria(tender_text: str) -> List[tuple[str, str]]:
        text = tender_text or ""
        section_match = re.search(
            r"(ELIGIBILITY\s+AND\s+TECHNICAL\s+QUALIFICATION\s+CRITERIA|ELIGIBILITY\s+CRITERIA|QUALIFICATION\s+CRITERIA)(?P<body>.*?)(DOCUMENTS\s+TO\s+BE\s+SUBMITTED|SCOPE\s+OF\s+WORK|FINANCIAL\s+BID|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        body = section_match.group("body") if section_match else text
        body = re.sub(r"\[PAGE\s+\d+(?:\s+OCR)?\]", " ", body, flags=re.IGNORECASE)
        item_matches = list(re.finditer(r"(?m)(?:^|\n)\s*(\d{1,2})\.\s+", body))
        extracted: List[tuple[str, str]] = []

        for index, match in enumerate(item_matches):
            start = match.end()
            end = item_matches[index + 1].start() if index + 1 < len(item_matches) else len(body)
            raw_item_text = body[start:end].strip()
            item_text = AIEvaluationService._clean_source_clause(raw_item_text)
            if not item_text:
                continue
            extracted.extend(AIEvaluationService._criteria_from_numbered_item(raw_item_text))

        return extracted

    @staticmethod
    def _criteria_from_numbered_item(item_text: str) -> List[tuple[str, str]]:
        source = AIEvaluationService._clean_source_clause(item_text)
        lower = source.lower()
        bullet_lines = re.findall(r"(?m)^\s*-\s*(.+?)\s*$", item_text)
        bullets = [AIEvaluationService._clean_source_clause(line) for line in bullet_lines if AIEvaluationService._clean_source_clause(line)]
        header = AIEvaluationService._clean_source_clause(re.split(r"(?m)^\s*-\s*", item_text, maxsplit=1)[0])

        if "at least" in lower and bullets:
            return [
                (f"{header} {bullet}", source)
                for bullet in bullets
                if AIEvaluationService._looks_like_tender_criterion_clause(f"{header} {bullet}")
            ]

        if ("should possess" in lower or "must possess" in lower or "valid:" in lower) and bullets:
            prefix = re.sub(r":\s*$", "", header)
            return [(f"{prefix} {bullet}", source) for bullet in bullets]

        if ("should provide" in lower or "must provide" in lower or "must submit" in lower or "should submit" in lower) and bullets:
            prefix = re.sub(r":\s*$", "", header)
            return [(f"{prefix} {bullet}", source) for bullet in bullets]

        if ("preference" in lower or "will be given" in lower) and bullets:
            return [(f"Preference will be given for {bullet}", source) for bullet in bullets]

        if AIEvaluationService._looks_like_tender_criterion_clause(source):
            return [(source, source)]
        return []

    @staticmethod
    def _looks_like_tender_criterion_clause(clause: str) -> bool:
        text = clause.lower()
        mandatory_or_submission = re.search(
            r"\b(shall|must|required|mandatory|eligible|eligibility|qualification|qualifying|"
            r"submit|submitted|furnish|furnished|provide|provided|attach|uploaded|should|preference)\b",
            text,
        )
        if not mandatory_or_submission:
            return False

        evidence_terms = [
            "bid security", "emd", "tender fee", "fee receipt", "bharat kosh",
            "power of attorney", "poa", "certificate", "registration", "gstin",
            "gst registration", "pan", "iso", "license", "licence", "undertaking",
            "declaration", "affidavit", "blacklisted", "blacklist", "litigation",
            "turnover", "net worth", "solvency", "financial statement", "balance sheet",
            "experience", "completion", "work order", "project", "technical capability",
            "methodology", "machinery", "manpower", "tax", "labour", "labor",
        ]
        return any(term in text for term in evidence_terms)

    @staticmethod
    def _infer_operator(description: str) -> Optional[str]:
        text = description.lower()
        if any(term in text for term in ["at least", "minimum", "not less than", "greater than", "more than"]):
            return ">="
        if "<=" in text or "not more than" in text:
            return "<="
        return None

    @staticmethod
    def _infer_numeric_value(description: str) -> Optional[float]:
        match = re.search(r"(?:at least|minimum|not less than|greater than|more than|>=)[^0-9₹]{0,80}(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)", description, re.IGNORECASE)
        if not match:
            match = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|projects?|crore|cr|lakh|lac|%)", description, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    @staticmethod
    def _infer_unit(description: str) -> Optional[str]:
        text = description.lower()
        if "crore" in text:
            return "crore"
        if "lakh" in text or "lac" in text:
            return "lakh"
        if "years" in text or "year" in text:
            return "years"
        if "projects" in text or "project" in text:
            return "projects"
        if "%" in text or "percent" in text:
            return "percentage"
        return None

    @staticmethod
    def _split_documentary_clause(clause: str) -> List[str]:
        text = AIEvaluationService._clean_source_clause(clause)
        lower = text.lower()
        if not re.search(r"\b(shall|must|required|submit|submitted|furnish|provide|attach)\b", lower):
            return [text]

        document_terms = [
            "bid security",
            "receipt of tender fee",
            "tender fee receipt",
            "tender fee",
            "power of attorney",
            "gst registration",
            "gst certificate",
            "pan registration",
            "pan card",
            "iso certificate",
            "registration certificate",
            "experience certificate",
            "completion certificate",
            "audited financial statements",
            "balance sheets",
            "technical capability statement",
            "project execution methodology",
            "list of machinery and manpower",
            "declaration",
            "undertaking",
            "affidavit",
        ]
        found = []
        for term in document_terms:
            if term == "tender fee" and any(existing.endswith("receipt of tender fee") or existing.endswith("tender fee receipt") for existing in found):
                continue
            if term in lower:
                found.append(f"The bidder must submit {term}")
        return found or [text]

    @staticmethod
    def _infer_criterion_type(description: str) -> str:
        text = description.lower()
        if any(term in text for term in ["turnover", "net worth", "financial", "balance sheet", "solvency"]):
            return "financial"
        if any(term in text for term in ["project", "experience", "technical", "methodology", "machinery", "manpower"]):
            return "technical"
        if any(term in text for term in ["gst", "pan", "iso", "registration", "license", "licence", "tax", "blacklist", "litigation"]):
            return "compliance"
        return "mandatory"

    @staticmethod
    def _is_mandatory_clause(description: str) -> bool:
        text = description.lower()
        if re.search(r"\b(may|preferably|desirable|preference)\b", text):
            return False
        return True

    @staticmethod
    def _page_near(full_text: str, snippet: str) -> Optional[int]:
        index = (full_text or "").find(snippet[:80])
        if index < 0:
            return None
        pages = list(re.finditer(r"\[PAGE\s+(\d+)(?:\s+OCR)?\]", full_text[:index], re.IGNORECASE))
        if not pages:
            return None
        return int(pages[-1].group(1))

    @staticmethod
    def _clean_source_clause(text: str) -> str:
        return re.sub(r"\s+", " ", str(text)).strip(" -:;")

    @staticmethod
    def _is_administrative_submission_item(description: str) -> bool:
        text = str(description).lower()
        administrative_terms = {
            "contact detail", "authorized representative", "authorised representative",
            "cover letter", "table of contents", "index", "page numbering",
            "file format", "upload", "sealed envelope", "hard copy", "soft copy",
        }
        if any(term in text for term in administrative_terms):
            return True
        if text.rstrip(" .:-").endswith(("having", "provide", "possess valid", "at least")):
            return True

        evidence_terms = {
            "gst", "pan", "iso", "license", "licence", "registration", "certificate",
            "turnover", "net worth", "financial", "balance sheet", "audited",
            "experience", "project", "blacklist", "litigation", "undertaking",
            "declaration", "affidavit", "solvency", "tax", "technical",
            "manpower", "machinery", "methodology",
        }
        if any(term in text for term in evidence_terms):
            return False

        if re.search(r"\b(?:minimum|at least|not less than|greater than|more than|>=|<=|\d+\s*(?:years?|crore|lakh|projects?|%))\b", text):
            return False

        return False

    @staticmethod
    async def extract_criteria_from_tender_legacy(tender_text: str) -> Dict[str, Any]:
        """Deprecated compatibility wrapper."""
        try:
            try:
                criteria_data = await AIEvaluationService.extract_criteria_from_tender(tender_text)
                logger.info(f"Extracted {len(criteria_data.get('criteria', []))} criteria from tender")
                return criteria_data
            except json.JSONDecodeError:
                logger.error("Failed to parse AI response as JSON")
                return {"criteria": []}
        
        except Exception as e:
            logger.error(f"Error extracting criteria: {e}")
            raise
    
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def extract_bidder_data(bidder_text: str) -> Dict[str, Any]:
        """
        Use AI to extract key information from bidder documents
        """
        prompt = f"""
        Analyze these bidder submission documents and extract key information. Be domain-neutral and preserve
        source evidence. Do not convert address numbers, phone numbers, pin codes, dates, invoice numbers,
        certificate numbers, or page numbers into eligibility values.
        Return a JSON object with the following structure:
        {{
            "company_info": {{
                "name": "...",
                "gst_number": "...",
                "pan_number": "...",
                "registration_number": "..."
            }},
            "financial": {{
                "turnover": numeric or null,
                "turnover_unit": "crore|lakh|etc",
                "net_profit": numeric or null,
                "bank_credit_rating": "..."
            }},
            "certifications": [
                {{
                    "name": "ISO-9001",
                    "valid": true|false,
                    "expiry_date": "YYYY-MM-DD"
                }}
            ],
            "project_experience": {{
                "similar_projects": numeric,
                "largest_project_value": numeric,
                "total_projects": numeric
            }},
            "compliance": {{
                "tax_compliance": true|false,
                "no_litigation": true|false,
                "labor_compliance": true|false
            }},
            "other_fields": {{
                "key": "value"
            }}
        }}
        
        Bidder Documents:
        {bidder_text[:8000]}
        
        Return ONLY valid JSON, no other text. For numeric values, extract only the number.
        """
        
        try:
            try:
                bidder_data = await AIEvaluationService._chat_json(prompt, max_tokens=2000)
                logger.info("Extracted bidder data successfully")
                return bidder_data
            except json.JSONDecodeError:
                logger.error("Failed to parse bidder data as JSON")
                return {}
        
        except Exception as e:
            logger.error(f"Error extracting bidder data: {e}")
            raise
    
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def evaluate_criterion(
        criterion_description: str,
        criterion_operator: Optional[str],
        criterion_value: Optional[float],
        extracted_value: Optional[str],
        bidder_context: str,
    ) -> Dict[str, Any]:
        """
        Evaluate if bidder meets a specific criterion
        """
        prompt = f"""
        Evaluate if a bidder meets a tender criterion.
        
        Criterion: {criterion_description}
        Criterion Operator: {criterion_operator}
        Criterion Required Value: {criterion_value}
        
        Extracted Bidder Value: {extracted_value}
        
        Bidder Context:
        {bidder_context[:2000]}
        
        Return a JSON object with the following structure:
        {{
            "matches": true|false,
            "confidence": 0.0 to 1.0,
            "reasoning": "explanation of the decision",
            "extracted_evidence": "the actual evidence from documents",
            "needs_manual_review": true|false,
            "manual_review_reason": "reason if manual review is needed"
        }}
        
        Return ONLY valid JSON, no other text.
        """
        
        try:
            try:
                evaluation = await AIEvaluationService._chat_json(prompt, max_tokens=500)
                return evaluation
            except json.JSONDecodeError:
                logger.error("Failed to parse evaluation as JSON")
                return {
                    "matches": False,
                    "confidence": 0.0,
                    "reasoning": "Evaluation parsing failed",
                    "needs_manual_review": True,
                }
        
        except Exception as e:
            logger.error(f"Error evaluating criterion: {e}")
            raise
    
    @staticmethod
    async def generate_decision_summary(
        overall_decision: str,
        criteria_results: List[CriterionEvaluation],
    ) -> str:
        """
        Generate a human-readable summary of evaluation decision
        """
        prompt = f"""
        Generate a concise executive summary of a tender evaluation decision.
        
        Overall Decision: {overall_decision}
        
        Criterion Results:
        {json.dumps([c.dict() for c in criteria_results], indent=2)}
        
        Write a 2-3 sentence summary explaining the decision based on the criteria evaluations.
        """
        
        try:
            return await AIEvaluationService._chat_text(prompt, max_tokens=300)
        
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Unable to generate summary due to an error."

    @staticmethod
    async def evaluate_bidder_submission(
        tender_text: str,
        bidder_text: str,
        tender_criteria: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a bidder against tender text and return an app-ready result.
        """
        criteria_context = json.dumps(tender_criteria or [], indent=2)
        prompt = f"""
        You are a conservative procurement eligibility evaluator for government tenders.
        Evaluate the bidder submission against the tender in a domain-neutral way. Prefer NEEDS_REVIEW over PASS
        when evidence is missing, ambiguous, expired, contradictory, unreadable, indirect, only implied, or legally unclear.

        Tender criteria already extracted from the tender, if any:
        {criteria_context}

        Tender document text:
        {tender_text[:7000]}

        Bidder document text:
        {bidder_text[:7000]}

        Rules:
        - Evaluate every explicit eligibility/qualification/compliance/financial/technical criterion you can identify.
        - Use the provided extracted criteria as the primary checklist.
        - Return exactly one criteria_results item for every provided extracted criterion. Keep the same meaning and preferably the same order.
        - If a provided criterion cannot be verified from bidder evidence, include it anyway with decision NEEDS_REVIEW.
        - Do not add criteria beyond the provided checklist. Missing tender criteria must be fixed during tender extraction, not during bidder evaluation.
        - Every PASS must cite concrete bidder evidence. If no exact source evidence exists, decision must be NEEDS_REVIEW.
        - For numeric thresholds, compare units carefully. Convert lakh/crore/INR where possible and explain conversion.
        - For project counts or experience counts, use only numbers directly tied to phrases like completed/executed/delivered projects, work orders, completion certificates, or years of experience.
        - Never use address numbers, office numbers, phone numbers, pin codes, GST/PAN digits, certificate numbers, dates, page numbers, invoice numbers, or reference numbers as eligibility values.
        - For legal/procurement language, distinguish mandatory terms (shall/must/required/eligible only if) from optional/preferential terms (may/preferably/desirable). Ambiguous clauses should be NEEDS_REVIEW.
        - For certificates/licenses/registrations, check whether validity/expiry is shown. If validity cannot be confirmed, use NEEDS_REVIEW unless tender only asks for presence.
        - For affidavits/declarations/undertakings, presence of similar words is not enough; cite the actual declaration or mark NEEDS_REVIEW.
        - For financial values, do not use project values as turnover/net worth unless the criterion asks for project value.
        - For past experience, do not use company age unless the criterion asks for years in operation.
        - Check validity dates for certificates, registrations, affidavits, solvency, tax documents, and experience letters.
        - Treat missing mandatory documents or unreadable OCR as NEEDS_REVIEW unless the tender clearly allows omission.
        - Treat conflicting bidder values as NEEDS_REVIEW and name the conflict in reasoning.
        - Do not mark overall eligible if any mandatory criterion is FAIL or NEEDS_REVIEW.
        - Set confidence below 0.7 when source evidence is weak, missing, or inferred.
        - Include source_document when the evidence appears to come from a specific section/document; otherwise use null.

        Return ONLY valid JSON with this exact structure:
        {{
            "overall_decision": "eligible|not_eligible|needs_manual_review",
            "overall_confidence": 0.0,
            "decision_summary": "2-3 sentence decision summary, including key anomalies or missing evidence",
            "criteria_results": [
                {{
                    "criterion": "criterion description",
                    "extracted_value": "value or evidence found, or null",
                    "source_document": "bidder submission",
                    "source_page": null,
                    "evidence_snippet": "short exact supporting snippet or null",
                    "decision": "PASS|FAIL|NEEDS_REVIEW",
                    "confidence": 0.0,
                    "reasoning": "short reason with evidence, threshold comparison, anomaly, or missing-document note"
                }}
            ]
        }}
        """

        try:
            data = await AIEvaluationService._chat_json(prompt, max_tokens=6000)
            data["_llm_evaluation_used"] = True
        except Exception as e:
            logger.error(f"Error evaluating bidder submission: {e}")
            return {
                "overall_decision": "needs_manual_review",
                "overall_confidence": 0.0,
                "decision_summary": "Evaluation could not be completed automatically. Manual review is required.",
                "criteria_results": [],
                "_llm_evaluation_used": False,
            }

        if data.get("overall_decision") not in {"eligible", "not_eligible", "needs_manual_review"}:
            data["overall_decision"] = "needs_manual_review"

        criteria_results = data.get("criteria_results") or []
        normalized_results = []
        has_fail = False
        has_review = False
        for item in criteria_results:
            decision = str(item.get("decision") or "NEEDS_REVIEW").upper()
            if decision not in {"PASS", "FAIL", "NEEDS_REVIEW"}:
                decision = "NEEDS_REVIEW"
            has_fail = has_fail or decision == "FAIL"
            has_review = has_review or decision == "NEEDS_REVIEW"
            extracted_value = item.get("extracted_value")
            evidence_snippet = item.get("evidence_snippet")
            source_document = item.get("source_document")
            if decision == "PASS" and not (extracted_value or evidence_snippet):
                decision = "NEEDS_REVIEW"
                has_review = True
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
            if decision == "PASS" and (not source_document or not evidence_snippet):
                confidence = min(confidence, 0.74)
            normalized_results.append({
                "criterion": item.get("criterion") or "Unspecified criterion",
                "extracted_value": extracted_value,
                "source_document": source_document,
                "source_page": item.get("source_page"),
                "evidence_snippet": evidence_snippet,
                "decision": decision,
                "confidence": confidence,
                "reasoning": item.get("reasoning") or "No reasoning provided.",
            })

        if has_fail:
            data["overall_decision"] = "not_eligible"
        elif has_review:
            data["overall_decision"] = "needs_manual_review"

        if normalized_results:
            normalized_results = AIEvaluationService._ensure_all_criteria_evaluated(
                normalized_results,
                tender_criteria or [],
            )
            normalized_results = AIEvaluationService.dedupe_evaluation_results(normalized_results)
            average_confidence = sum(item["confidence"] for item in normalized_results) / len(normalized_results)
            data["overall_confidence"] = max(0.0, min(1.0, average_confidence))
        else:
            normalized_results = AIEvaluationService._ensure_all_criteria_evaluated(
                [],
                tender_criteria or [],
            )
            normalized_results = AIEvaluationService.dedupe_evaluation_results(normalized_results)
            data["overall_confidence"] = max(0.0, min(1.0, float(data.get("overall_confidence") or 0.0)))
        if any(item.get("decision") == "FAIL" for item in normalized_results):
            data["overall_decision"] = "not_eligible"
        elif any(item.get("decision") == "NEEDS_REVIEW" for item in normalized_results):
            data["overall_decision"] = "needs_manual_review"
        data["decision_summary"] = data.get("decision_summary") or "Evaluation completed."
        data["criteria_results"] = normalized_results
        return data

    @staticmethod
    def align_results_to_criteria(
        results: List[Dict[str, Any]],
        tender_criteria: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return exactly one result per stored tender criterion, in tender order."""
        if not tender_criteria:
            return AIEvaluationService.dedupe_evaluation_results(results)

        remaining = list(AIEvaluationService.dedupe_evaluation_results(results))
        aligned: List[Dict[str, Any]] = []

        for criterion in tender_criteria:
            description = criterion.get("criterion") or criterion.get("description") or "Tender criterion"
            mandatory = bool(criterion.get("mandatory", criterion.get("is_mandatory", True)))
            match_index = AIEvaluationService._best_result_match(description, remaining)

            if match_index is None:
                aligned.append({
                    "criterion": description,
                    "extracted_value": None,
                    "source_document": None,
                    "source_page": None,
                    "evidence_snippet": None,
                    "mandatory": mandatory,
                    "decision": "NEEDS_REVIEW",
                    "confidence": 0.35,
                    "reasoning": "This stored tender criterion was not evaluated with concrete bidder evidence. Manual review is required.",
                })
                continue

            item = remaining.pop(match_index)
            item["criterion"] = description
            item["mandatory"] = mandatory
            aligned.append(item)

        return aligned

    @staticmethod
    def finalize_evaluation_decision(data: Dict[str, Any]) -> Dict[str, Any]:
        results = data.get("criteria_results") or []
        mandatory_results = [item for item in results if item.get("mandatory", True)]
        decision_rows = mandatory_results or results
        if any(item.get("decision") == "FAIL" for item in decision_rows):
            data["overall_decision"] = "not_eligible"
        elif any(item.get("decision") == "NEEDS_REVIEW" for item in decision_rows):
            data["overall_decision"] = "needs_manual_review"
        else:
            data["overall_decision"] = "eligible"

        confidences = [float(item.get("confidence") or 0.0) for item in results]
        data["overall_confidence"] = (sum(confidences) / len(confidences)) if confidences else 0.0
        fail_count = sum(1 for item in results if item.get("decision") == "FAIL")
        review_count = sum(1 for item in results if item.get("decision") == "NEEDS_REVIEW")
        data["decision_summary"] = (
            f"Hybrid evaluation completed across {len(results)} stored tender criteria. "
            f"{fail_count} failed and {review_count} require manual review."
        )
        return data

    @staticmethod
    def _best_result_match(description: str, results: List[Dict[str, Any]]) -> Optional[int]:
        criterion_key = AIEvaluationService._criterion_key(description)
        criterion_words = set(AIEvaluationService._criterion_keywords(description))
        best_index = None
        best_score = 0.0

        for index, item in enumerate(results):
            result_description = item.get("criterion") or ""
            if criterion_key and criterion_key == AIEvaluationService._criterion_key(result_description):
                return index

            result_words = set(AIEvaluationService._criterion_keywords(result_description))
            if AIEvaluationService._looks_like_same_criterion(criterion_words, result_words):
                overlap = len(criterion_words.intersection(result_words))
                union = len(criterion_words.union(result_words)) or 1
                score = overlap / union
                if score > best_score:
                    best_score = score
                    best_index = index

        return best_index

    @staticmethod
    def _ensure_all_criteria_evaluated(
        normalized_results: List[Dict[str, Any]],
        tender_criteria: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Guarantee one result row for every extracted tender criterion."""
        completed = list(normalized_results)
        existing_keys = {
            AIEvaluationService._criterion_key(item.get("criterion", ""))
            for item in completed
            if AIEvaluationService._criterion_key(item.get("criterion", ""))
        }
        existing_words = [
            set(AIEvaluationService._criterion_keywords(item.get("criterion", "")))
            for item in completed
        ]

        for criterion in tender_criteria:
            description = criterion.get("criterion") or criterion.get("description") or "Tender criterion"
            key = AIEvaluationService._criterion_key(description)
            if key and key in existing_keys:
                continue
            words = set(AIEvaluationService._criterion_keywords(description))
            duplicate = any(
                words and AIEvaluationService._looks_like_same_criterion(words, item_words)
                for item_words in existing_words
            )
            if duplicate:
                continue
            completed.append({
                "criterion": description,
                "extracted_value": None,
                "source_document": None,
                "source_page": None,
                "evidence_snippet": None,
                "decision": "NEEDS_REVIEW",
                "confidence": 0.35,
                "reasoning": "This extracted tender criterion was not evaluated with concrete bidder evidence. Manual review is required.",
            })
            if key:
                existing_keys.add(key)
            existing_words.append(words)

        return completed

    @staticmethod
    def dedupe_evaluation_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collapse repeated results for the same tender criterion, keeping the strongest evidence."""
        deduped: List[Dict[str, Any]] = []
        positions: Dict[str, int] = {}
        seen_words: List[set] = []

        for item in results:
            criterion = item.get("criterion") or ""
            key = AIEvaluationService._criterion_key(criterion)
            index = positions.get(key) if key else None
            if index is None:
                words = set(AIEvaluationService._criterion_keywords(criterion))
                for existing_index, existing_words in enumerate(seen_words):
                    if words and AIEvaluationService._looks_like_same_criterion(words, existing_words):
                        index = existing_index
                        break

            if index is None:
                if key:
                    positions[key] = len(deduped)
                seen_words.append(set(AIEvaluationService._criterion_keywords(criterion)))
                deduped.append(item)
            else:
                deduped[index] = AIEvaluationService._prefer_stronger_result(deduped[index], item)

        return deduped

    @staticmethod
    def _prefer_stronger_result(current: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        def score(item: Dict[str, Any]) -> tuple:
            decision = str(item.get("decision") or "NEEDS_REVIEW").upper()
            decision_score = {"PASS": 3, "NEEDS_REVIEW": 2, "FAIL": 1}.get(decision, 0)
            evidence_score = int(bool(item.get("extracted_value"))) + int(bool(item.get("evidence_snippet")))
            confidence = float(item.get("confidence") or 0.0)
            return (evidence_score, decision_score, confidence)

        stronger, weaker = (candidate, current) if score(candidate) > score(current) else (current, candidate)
        merged = {**weaker, **stronger}
        for key in ("extracted_value", "source_document", "source_page", "evidence_snippet"):
            merged[key] = stronger.get(key) or weaker.get(key)
        if weaker.get("reasoning") and weaker.get("reasoning") not in str(stronger.get("reasoning")):
            merged["reasoning"] = f"{stronger.get('reasoning', '')} Additional duplicate finding: {weaker.get('reasoning')}"
        return merged

    @staticmethod
    def _criterion_keywords(description: str) -> List[str]:
        stop_words = {
            "shall", "must", "have", "with", "from", "last", "years", "minimum",
            "required", "bidder", "bidders", "tender", "criteria", "criterion",
            "valid",
        }
        return [
            word
            for word in re.findall(r"[A-Za-z0-9]{3,}", str(description).lower())
            if word not in stop_words
        ][:16]

    @staticmethod
    def _criterion_key(description: str) -> str:
        tokens = AIEvaluationService._criterion_keywords(description)
        important_short_tokens = {"gst", "pan", "iso", "msme", "epf", "esi", "esic"}
        short_hits = sorted(token for token in tokens if token in important_short_tokens)
        if short_hits:
            return "identifier:" + ":".join(short_hits)
        normalized = re.sub(r"[^a-z0-9]+", " ", str(description).lower()).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    @staticmethod
    def _looks_like_same_criterion(words: set, existing: set) -> bool:
        if not words or not existing:
            return False
        important_short_tokens = {"gst", "pan", "iso", "msme", "epf", "esi", "esic"}
        if words.intersection(existing).intersection(important_short_tokens):
            return True
        overlap = len(words.intersection(existing))
        union = len(words.union(existing))
        jaccard = overlap / union if union else 0.0
        return overlap >= 5 and jaccard >= 0.85
