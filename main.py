import time
import requests
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from predictions import calculate_item_projections

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SUAS CHAVES DO SUPABASE ---
SUPABASE_URL = "https://rzqfomsygtiwtzghkwlt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ6cWZvbXN5Z3Rpd3R6Z2hrd2x0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY1MzI0NzIsImV4cCI6MjEwMjEwODQ3Mn0.3j1E7fjmVWV-NjsSQvMa4iIdohoZDJYGdzkLKuldl4w"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

IGNORED_KEYWORDS = [
    "Sticker |", "Adesivo |", 
    "Sealed Graffiti |", "Graffiti |", 
    "Patch |", "Emblema |", 
    "Music Kit |", "Kit de Música |", 
    "Charm |", "Chaveiro |",
    "Pass", "Passe", "Viewer Pass"
]

def fetch_steam_market_catalog(pages=100):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    all_items = []
    results_per_page = 100
    
    for page in range(pages):
        start = page * results_per_page
        url = f"https://steamcommunity.com/market/search/render/?query=&start={start}&count={results_per_page}&search_descriptions=0&sort_column=popular&sort_dir=desc&appid=730&norender=1"
        
        try:
            print(f"🌐 Consultando Mercado da Steam (Página {page + 1}/{pages})...")
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                results = data.get("results", [])
                if not results:
                    break
                all_items.extend(results)
                time.sleep(1.2)
            else:
                print(f"⚠️ Erro HTTP {res.status_code} na página {page + 1}")
                break
        except Exception as e:
            print(f"❌ Erro na página {page + 1}: {e}")
            break
            
    return all_items

def sync_all_skins_task():
    print("\n🔄 Limpando e ressincronizando imagens, oportunidades e projeções...")
    steam_items = fetch_steam_market_catalog(pages=100)

    if not steam_items:
        print("❌ Não foi possível carregar os itens.")
        return

    count = 0
    ignored_count = 0

    for item in steam_items:
        skin_name = item.get("hash_name") or item.get("name", "")
        if not skin_name:
            continue

        if any(keyword.lower() in skin_name.lower() for keyword in IGNORED_KEYWORDS):
            ignored_count += 1
            continue

        raw_price_str = item.get("sell_price_text", "0")
        raw_p = raw_price_str.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try:
            current_price = float(raw_p) if raw_p else 0.0
        except ValueError:
            current_price = 0.0

        if current_price == 0.0:
            current_price = (item.get("sell_price", 0) or 0) / 100.0

        if current_price < 2.00:
            ignored_count += 1
            continue

        icon_url = item.get("asset_description", {}).get("icon_url", "")
        if not icon_url:
            ignored_count += 1
            continue
            
        # URL da imagem direta do Cloudflare CDN da Steam
        image_url = f"https://community.cloudflare.steamstatic.com/economy/image/{icon_url}"

        if "Knife" in skin_name or "★" in skin_name or "Faca" in skin_name or "Bayonet" in skin_name or "Karambit" in skin_name or "Butterfly" in skin_name:
            category = "Faca"
        elif "Gloves" in skin_name or "Luvas" in skin_name or "Hand Wraps" in skin_name:
            category = "Luva"
        elif "Case" in skin_name or "Caixa" in skin_name:
            category = "Caixa"
        elif "Agent" in skin_name or "Agente" in skin_name:
            category = "Agente"
        else:
            category = "Skin"

        avg_price = round(current_price * 1.08, 2)
        discount = round(((avg_price - current_price) / avg_price) * 100, 2)
        trend_score = min(100.0, max(0.0, 50.0 + (discount * 1.5)))
        steam_link = f"https://steamcommunity.com/market/listings/730/{requests.utils.quote(skin_name)}"
        daily_volume = item.get("sell_listings", 150)

        # Cálculo Preditivo
        projections = calculate_item_projections(
            current_price=current_price,
            avg_30d=avg_price,
            daily_volume=daily_volume,
            category=category
        )

        try:
            # 1. Salva na tabela skins
            skin_payload = {
                "market_hash_name": skin_name,
                "category": category,
                "image_url": image_url
            }
            check_skin = supabase.table("skins").select("id").eq("market_hash_name", skin_name).execute()
            if check_skin.data:
                supabase.table("skins").update(skin_payload).eq("market_hash_name", skin_name).execute()
            else:
                supabase.table("skins").insert(skin_payload).execute()

            # 2. Salva na tabela skin_opportunities INCLUINDO Projeções Futuras
            opportunity_data = {
                "market_hash_name": skin_name,
                "current_price": current_price,
                "avg_price_7d": avg_price,
                "avg_price_30d": avg_price,
                "discount_pct": discount,
                "daily_volume": daily_volume,
                "trend_score": round(trend_score, 1),
                "trend_label": "Alta Probabilidade" if trend_score >= 60 else "Estável",
                "steam_url": steam_link,
                "image_url": image_url,
                "category": category,
                "projected_30d": projections["projected_30d"] if projections else None,
                "projected_90d": projections["projected_90d"] if projections else None,
                "projected_365d": projections["projected_365d"] if projections else None,
                "confidence": projections["confidence"] if projections else "BAIXA"
            }
            check_opp = supabase.table("skin_opportunities").select("id").eq("market_hash_name", skin_name).execute()
            if check_opp.data:
                supabase.table("skin_opportunities").update(opportunity_data).eq("market_hash_name", skin_name).execute()
            else:
                supabase.table("skin_opportunities").insert(opportunity_data).execute()

            count += 1
            if count % 25 == 0:
                print(f"✅ [{count}] Skins e projeções salvas...")

        except Exception as e:
            print(f"⚠️ Erro ao salvar {skin_name}: {e}")

    print(f"\n🎉 Concluído! Total: {count} skins atualizadas com projeções.")

@app.get("/")
def home():
    return {"status": "Servidor rodando!"}

@app.get("/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_all_skins_task)
    return {"status": "Sincronização iniciada em segundo plano com sucesso!"}
