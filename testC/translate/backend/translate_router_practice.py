from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal
import sys
import os

# 引入正式后端的 ai_service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../back_mic/backend"))
from ai_search.ai_service import AISearchService
import anthropic

router = APIRouter()
service = AISearchService()
from dotenv import load_dotenv
load_dotenv(r"D:\copypan\back_mic\backend\.env")
claude = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))

# 英译西语术语表
EN_ES_TERMS = {
    "All-Inclusive Christ": "El Cristo todo-inclusivo",
    "The Triune God": "El Dios Triuno",
    "The God-man": "El Dios-hombre",
    "Incarnation, inclusion, and intensification": "La encarnación, la inclusión y la intensificación",
    "The Spirit": "El Espíritu",
    "Compound Spirit": "El Espíritu compuesto",
    "Life-giving Spirit": "El Espíritu vivificante",
    "Mingled Spirit": "El Espíritu mezclado",
    "Anointing": "La unción",
    "Morning revival": "El avivamiento matutino",
    "The Holy Word for Morning Revival": "La palabra santa para el avivamiento matutino",
    "Semiannual Training": "El entrenamiento semianual",
    "The Memorial Day Conference": "La conferencia del Día de Conmemoración",
    "Conference": "La conferencia",
    "The Lord's table meeting": "La reunión de la mesa del Señor",
    "Blending": "La compenetración",
    "Small group meetings": "Las reuniones de grupos pequeños",
    "Vital groups": "Los grupos vitales",
    "Hymn": "El himno",
    "Bride": "La novia",
    "The Lord's recovery": "El recobro del Señor",
    "New creation": "La nueva creación",
    "Old creation": "La vieja creación",
    "Good land": "La buena tierra",
    "Mutuality": "La mutualidad",
    "Millennium": "El milenio",
    "New Testament economy": "La economía neotestamentaria",
    "Ministry": "El ministerio",
    "Recovery Version Bible": "La Santa Biblia Versión Recobro",
    "Organic": "Orgánico",
    "Disciple": "El discípulo",
    "Firstfruit": "Las primicias",
    "Regenerate": "La regeneración",
    "Ultimate consummation": "La consumación máxima",
    "Uncreated life": "La vida increada",
    "Full salvation": "La salvación plena",
    "Rapture": "El arrebatamiento",
    "Godliness": "La piedad",
    "Habitation": "La morada",
    "Coinherence": "La morada mutua",
    "Mutual abiding": "La morada mutua",
    "Spiritual warfare": "La guerra espiritual",
    "Corporate Christ": "El Cristo corporativo",
    "Deputy authority": "La autoridad delegada",
    "Consecration": "La consagración",
    "Apostle": "El apóstol",
    "Deacon": "El diácono",
    "Coordinate": "Coordinar",
    "Preach the gospel": "Predicar el evangelio",
    "Evangelist": "El evangelista",
    "Intercessor": "El intercesor",
    "Constructive economy": "La economía constructiva",
    "Kingship and headship": "El señorío y la jefatura",
    "The faithful word": "La palabra fiel",
    "Dispense": "Dispensar",
    "Feast": "La fiesta",
    "Love feast": "La fiesta de amor",
    "Meeting hall": "El salón de reuniones",
    "In-person": "Presencial",
    "Watchman Nee": "Watchman Nee",
    "Spirituality": "La espiritualidad",
    "Parousia": "La Parusía",
    "Messiah": "El Mesías",
    "Martyrdom": "El martirio",
    "Fragrance": "La fragancia",
    "Division": "La disensión",
    "Degradation": "La degradación",
    "Enlighten": "Iluminar",
    "Human virtue": "Las virtudes humanas",
    "Iniquity": "La iniquidad",
    "Foreknowledge": "La presciencia",
    "Exhort": "Exhortar",
    "Wedding feast": "El banquete de bodas",
    "Baptism": "El bautismo",
    "Crystallization": "La cristalización",
    "Conscience": "La conciencia",
    "Authority": "La autoridad",
    "Comforter": "El Consolador",
    "Holy of Holies": "El Lugar Santísimo",
    "Zion": "Sión",
    "Tripartite man": "El hombre tripartito",
    "Sabbath": "El sábado",
    "Lamb": "El Cordero",
    "Scripture reading": "Lectura bíblica",
}


def translate_en2es(content: str) -> dict:
    """英文翻译为西班牙文，使用术语表 + Claude"""
    # 构建术语表说明
    terms_str = "\n".join([f"{k}\t{v}" for k, v in EN_ES_TERMS.items()])
    prompt = f"""你是一个专业的英文翻西班牙文助手。以下是术语表，请在翻译中严格使用：

英文翻西班牙文专用术语表：
{terms_str}

请将以下英文内容翻译为西班牙文，严格使用以上术语表，保持纲目结构和层级不变，只输出翻译结果，不要加任何解释：

{content}"""

    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return {"result": message.content[0].text, "error": None}


class TranslateRequest(BaseModel):
    direction: Literal["zh2en", "en2zh", "en2es"]  # 翻译方向
    content: str                                     # 待翻译内容


@router.post("/practice/translate")
async def practice_translate(req: TranslateRequest):
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    if len(req.content) > 100000:
        raise HTTPException(status_code=400, detail="content 不能超过 100000 字")

    if req.direction == "zh2en":
        res = service.translate_outline(req.content)
        return {"result": res.get("answer_en") or res.get("result", ""), "error": res.get("error")}
    elif req.direction == "en2zh":
        res = service.translate_outline_en2zh(req.content)
        return {"result": res.get("answer_zh") or res.get("result", ""), "error": res.get("error")}
    else:  # en2es
        return translate_en2es(req.content)
