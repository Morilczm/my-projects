import json
import os
import urllib.error
import urllib.request


class AIProvider:
    provider_name = "base"
    is_real_provider = False

    def extract_terms(self, text_chunks, course_context=None):
        return []

    def generate_translation_candidate(self, english_term, english_evidence=None):
        return english_term

    def align_bilingual_evidence(
        self,
        english_term,
        course,
        chapter,
        courseware_sentence,
        english_evidence,
        translation_candidate_hint,
        chinese_evidence
    ):
        return {
            "ai_translation_candidate": translation_candidate_hint or english_term,
            "final_chinese_term": translation_candidate_hint or english_term,
            "explanation": "",
            "confidence_score": 50,
            "alignment_reason": "MockProvider fallback alignment.",
            "review_status": "pending_quality_control",
            "risk_note": "AI provider fallback result."
        }

    def student_answer(self, question, course, english_evidence, chinese_evidence, personal_evidence):
        return {
            "answer": "MockProvider fallback: evidence is available, but no live model response was generated.",
            "key_terms": [],
            "personalized_note": "",
            "study_suggestion": "Review the bilingual evidence cards and mark confusing terms for feedback.",
            "evidence_summary": "Local fallback answer generated from retrieved evidence.",
            "confidence": 45,
            "risk_note": "Mock AI response."
        }


class MockProvider(AIProvider):
    provider_name = "mock"
    is_real_provider = False

    def extract_terms(self, text_chunks, course_context=None):
        text = "\n".join(
            chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
            for chunk in text_chunks
        )
        candidates = []
        for phrase in (
            "Hash Table",
            "Hash Function",
            "Collision Resolution",
            "Angular Frequency",
            "Wavelength",
            "Knowledge Alignment"
        ):
            if phrase.lower() in text.lower():
                candidates.append(phrase)
        return candidates[:8]

    def generate_translation_candidate(self, english_term, english_evidence=None):
        mapping = {
            "hash table": "哈希表",
            "hash function": "哈希函数",
            "collision resolution": "冲突解决",
            "angular frequency": "角频率",
            "wavelength": "波长",
            "knowledge alignment": "知识对齐"
        }
        return mapping.get(str(english_term or "").strip().lower(), english_term)

    def align_bilingual_evidence(
        self,
        english_term,
        course,
        chapter,
        courseware_sentence,
        english_evidence,
        translation_candidate_hint,
        chinese_evidence
    ):
        final_term = translation_candidate_hint or self.generate_translation_candidate(english_term)
        has_english = bool(english_evidence)
        has_chinese = bool(chinese_evidence)
        confidence = 62 if has_english and has_chinese else 45 if has_english or has_chinese else 30
        return {
            "ai_translation_candidate": final_term,
            "final_chinese_term": final_term,
            "explanation": "MockProvider: generated from parsed chunks and retrieved bilingual evidence.",
            "confidence_score": confidence,
            "alignment_reason": (
                "MockProvider compared available English and Chinese evidence. "
                "Use DeepSeekProvider for stronger semantic judgement."
            ),
            "review_status": "pending_quality_control",
            "risk_note": "Mock AI is for local demonstration only; no live AI provider completed semantic alignment."
        }

    def student_answer(self, question, course, english_evidence, chinese_evidence, personal_evidence):
        key_terms = []
        for item in (english_evidence or [])[:2]:
            text = item.get("content", "") if isinstance(item, dict) else str(item)
            if text:
                key_terms.append(text.split()[0][:40])
        return {
            "answer": "MockProvider: retrieved course and personal evidence is shown below. The live model is not required for local demonstration.",
            "key_terms": key_terms,
            "personalized_note": "Personal workspace evidence was included only when it belonged to the current user.",
            "study_suggestion": "Open the terminology cards, compare both evidence quotes, then mark mastered terms.",
            "evidence_summary": f"English evidence: {len(english_evidence or [])}; Chinese evidence: {len(chinese_evidence or [])}; personal evidence: {len(personal_evidence or [])}.",
            "confidence": 55,
            "risk_note": "Mock AI response."
        }


class DeepSeekProvider(AIProvider):
    provider_name = "deepseek"
    is_real_provider = True

    def __init__(self, api_key, base_url, model):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")
        self.model = (model or "deepseek-v4-flash").strip()
        try:
            self.timeout_seconds = max(3, min(60, int(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "15"))))
        except ValueError:
            self.timeout_seconds = 15

    def _call_json(self, system_prompt, user_payload, max_tokens=1600):
        if not self.api_key:
            raise RuntimeError("Missing DeepSeek API key.")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "temperature": 0.2,
            "max_tokens": max_tokens
        }

        request_obj = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(request_obj, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DeepSeek API network error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"DeepSeek API timeout after {self.timeout_seconds}s.") from exc

        content = (
            response_payload
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        if not content:
            raise RuntimeError("DeepSeek API returned empty content.")

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(content[start:end + 1])

    def extract_terms(self, text_chunks, course_context=None):
        system_prompt = """
You are LexiBridge AI's term extraction engine for bilingual course knowledge alignment.
Extract only professional academic English terms or noun phrases from parsed course chunks.
Do not return full sentences, verb phrases, OCR placeholders, or generic descriptive fragments.
Return valid JSON only:
{
  "terms": [
    {
      "english_term": "string",
      "context_sentence": "string",
      "reason": "string",
      "confidence": 0
    }
  ]
}
""".strip()
        payload = {
            "course_context": course_context or {},
            "chunks": text_chunks[:20]
        }
        result = self._call_json(system_prompt, payload, max_tokens=1800)
        terms = result.get("terms", [])
        if not isinstance(terms, list):
            return []
        cleaned = []
        for item in terms:
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "english_term": str(item.get("english_term", "")).strip(),
                "context_sentence": str(item.get("context_sentence", "")).strip(),
                "reason": str(item.get("reason", "")).strip(),
                "confidence": int(item.get("confidence", 0) or 0)
            })
        return cleaned

    def align_bilingual_evidence(
        self,
        english_term,
        course,
        chapter,
        courseware_sentence,
        english_evidence,
        translation_candidate_hint,
        chinese_evidence
    ):
        system_prompt = """
You are LexiBridge AI, a bilingual course knowledge alignment engine.
You do not simply translate. You compare English courseware, English textbook evidence, and Chinese textbook evidence.
Return valid JSON only:
{
  "ai_translation_candidate": "string",
  "final_chinese_term": "string",
  "explanation": "string",
  "confidence_score": 0,
  "alignment_reason": "string",
  "review_status": "auto_approved|pending_quality_control|needs_more_evidence|conflict_detected|rejected",
  "risk_note": "string"
}
If evidence is weak or conflicting, lower confidence and put the result into pending_quality_control.
""".strip()

        result = self._call_json(system_prompt, {
            "english_term": english_term,
            "course": course,
            "chapter": chapter,
            "courseware_sentence": courseware_sentence,
            "english_textbook_evidence": english_evidence,
            "translation_candidate_hint": translation_candidate_hint,
            "chinese_textbook_evidence": chinese_evidence
        }, max_tokens=1500)

        confidence = int(result.get("confidence_score", 0) or 0)
        result["confidence_score"] = max(0, min(confidence, 100))
        return result

    def student_answer(self, question, course, english_evidence, chinese_evidence, personal_evidence):
        system_prompt = """
You are LexiBridge AI's student learning assistant. Return valid JSON only:
{
  "answer": "string",
  "key_terms": ["string"],
  "personalized_note": "string",
  "study_suggestion": "string",
  "evidence_summary": "string",
  "confidence": 0,
  "risk_note": "string"
}
Use only provided evidence. If evidence is weak, say so.
""".strip()

        result = self._call_json(system_prompt, {
            "course": course,
            "question": question,
            "english_course_evidence": english_evidence,
            "chinese_course_evidence": chinese_evidence,
            "student_personal_evidence": personal_evidence
        }, max_tokens=1800)

        confidence = int(result.get("confidence", 0) or 0)
        result["confidence"] = max(0, min(confidence, 100))
        return result


class NotImplementedProvider(AIProvider):
    is_real_provider = False
    provider_name = "not-implemented"

    def extract_terms(self, text_chunks, course_context=None):
        raise NotImplementedError(f"{self.provider_name} is not implemented in this Local MVP.")

    def align_bilingual_evidence(self, *args, **kwargs):
        raise NotImplementedError(f"{self.provider_name} is not implemented in this Local MVP.")

    def student_answer(self, *args, **kwargs):
        raise NotImplementedError(f"{self.provider_name} is not implemented in this Local MVP.")


class OpenAIProvider(NotImplementedProvider):
    provider_name = "openai-placeholder"


class GeminiProvider(NotImplementedProvider):
    provider_name = "gemini-placeholder"


class ClaudeProvider(NotImplementedProvider):
    provider_name = "claude-placeholder"


def get_ai_provider(provider_name, api_key="", base_url="", model=""):
    provider_name = (provider_name or "mock").strip().lower()

    if provider_name == "deepseek" and api_key:
        return DeepSeekProvider(api_key=api_key, base_url=base_url, model=model)

    if provider_name == "openai":
        return OpenAIProvider()

    if provider_name == "gemini":
        return GeminiProvider()

    if provider_name == "claude":
        return ClaudeProvider()

    return MockProvider()
