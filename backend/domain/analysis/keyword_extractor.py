
import re

from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_MD_IMAGE = re.compile(r"!\[.*?\]\(.+?\)")
_URL = re.compile(r"https?://\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_ORCID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")
_MD_FORMAT = re.compile(r"[*_#|`>]")
_MULTI_SPACE = re.compile(r"\s+")

def _clean_for_keywords(text: str) -> str:
    text = _MD_IMAGE.sub("", text)
    text = _URL.sub("", text)
    text = _EMAIL.sub("", text)
    text = _ORCID.sub("", text)
    text = _MD_FORMAT.sub(" ", text)
    return _MULTI_SPACE.sub(" ", text).strip()

class KeywordModelFactory:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_model(self):
        if self._model is None:
            with timer("Load KeyBERT model"):
                from keybert import KeyBERT
                self._model = KeyBERT(model="all-MiniLM-L6-v2")
                logger.info("KeyBERT model loaded into memory")
        return self._model

    def unload(self) -> None:
        if self._model is not None:
            self._model = None
            logger.info("KeyBERT model unloaded from memory")

def _get_kw_model():
    factory = KeywordModelFactory()
    return factory.get_model()

def unload_kw_model() -> None:
    factory = KeywordModelFactory()
    factory.unload()
    logger.info("KeyBERT model unloaded from memory via factory")

def extract_keywords(
    text: str,
    top_n: int = 10,
    keyphrase_ngram_range: tuple[int, int] = (1, 3),
    use_mmr: bool = True,
    diversity: float = 0.5,
) -> list[dict]:
    if not text or len(text.strip()) < 50:
        return []

    cleaned = _clean_for_keywords(text)
    if len(cleaned) < 50:
        return []

    kw_model = _get_kw_model()

    keywords = kw_model.extract_keywords(
        cleaned,
        keyphrase_ngram_range=keyphrase_ngram_range,
        stop_words="english",
        top_n=top_n,
        use_mmr=use_mmr,
        diversity=diversity,
    )

    results = [{"keyword": kw, "score": round(score, 4)} for kw, score in keywords]
    logger.info(f"Extracted {len(results)} keywords")
    return results

def extract_keywords_per_paper(
    paper_texts: dict[str, str],
    top_n: int = 10,
) -> dict[str, list[dict]]:
    return {
        pid: extract_keywords(text, top_n=top_n)
        for pid, text in paper_texts.items()
    }
