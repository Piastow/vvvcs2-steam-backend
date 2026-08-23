# predictions.py
import math

def calculate_item_projections(current_price: float, avg_30d: float, daily_volume: int, category: str):
    """
    Gera estimativas de preço futuro para 30, 90 e 365 dias com base no perfil do item.
    """
    if not current_price or current_price <= 0:
        return None

    avg_30d = avg_30d if avg_30d and avg_30d > 0 else current_price

    # 1. Média Móvel / Tendência Recente
    base_trend = (current_price / avg_30d) - 1.0

    # 2. Multiplicador por Categoria (Adesivos e Caixas tendem a valorizar por consumo)
    category_multiplier = 1.0
    cat_lower = (category or "").lower()
    
    if "sticker" in cat_lower or "adesivo" in cat_lower:
        category_multiplier = 1.12
    elif "case" in cat_lower or "caixa" in cat_lower:
        category_multiplier = 1.20
    elif "knife" in cat_lower or "faca" in cat_lower or "gloves" in cat_lower:
        category_multiplier = 1.05

    # 3. Fator de Giro/Escassez
    vol = max(daily_volume or 1, 1)
    scarcity_factor = math.log10(vol + 1) / 10.0

    # 4. Cálculo da taxa diária de crescimento esperada
    annual_growth_rate = (base_trend * 0.2) + (category_multiplier * 0.08) - (scarcity_factor * 0.01)

    def predict_for_days(days: int):
        # Curva suave
        daily_rate = annual_growth_rate / 365.0
        projected = current_price * math.pow(1.0 + daily_rate, days)
        return round(max(projected, current_price * 0.5), 2)

    pred_30d = predict_for_days(30)
    pred_90d = predict_for_days(90)
    pred_365d = predict_for_days(365)

    # Nível de confiança da estimativa
    confidence = "ALTA" if vol > 50 and avg_30d > 0 else "MEDIA" if vol > 10 else "BAIXA"

    return {
        "projected_30d": pred_30d,
        "projected_90d": pred_90d,
        "projected_365d": pred_365d,
        "confidence": confidence
    }
