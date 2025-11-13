import os
import signal
import requests
import json
import traceback
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# --- Configuración ---
SHOPIFY_STORE_URL = os.getenv('SHOPIFY_SHOP_URL')
SHOPIFY_ACCESS_TOKEN = os.getenv('SHOPIFY_TOKEN_API_ADMIN')
API_VERSION = os.getenv('SHOPIFY_API_VERSION', '2025-10')

if not SHOPIFY_STORE_URL or not SHOPIFY_ACCESS_TOKEN:
    raise ValueError("SHOPIFY_SHOP_URL y SHOPIFY_TOKEN_API_ADMIN deben estar configurados.")

# --- Configuración de GraphQL ---
GRAPHQL_ENDPOINT = f"{SHOPIFY_STORE_URL}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {
    'X-Shopify-Access-Token': SHOPIFY_ACCESS_TOKEN,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

def run_shopify_query(query, variables):
    payload = {'query': query, 'variables': variables}
    print(f"   [GraphQL] Ejecutando consulta/mutación...")
    print(f"   [GraphQL] Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(GRAPHQL_ENDPOINT, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if 'errors' in data:
            print(f"❌ Error en la respuesta de GraphQL: {data['errors']}")
            return None
            
        print("   [GraphQL] Respuesta recibida con éxito.")
        return data.get('data')
        
    except requests.exceptions.HTTPError as http_err:
        print(f"❌ Error HTTP: {http_err}")
        print(f"   Detalle de la respuesta: {response.text}")
    except requests.exceptions.RequestException as req_err:
        print(f"❌ Error de Conexión: {req_err}")
    except Exception as e:
        print(f"❌ Error inesperado en 'run_shopify_query': {e}")
        traceback.print_exc()
    return None

# --- Consultas y Mutaciones de GraphQL ---

# PASO 1 (Query A):
GET_LOCATION_QUERY = """
query getFirstLocation {
  locations(first: 1) {
    edges {
      node {
        id
        name
      }
    }
  }
}
"""

# PASO 1 (Query B):
GET_DATA_QUERY = """
query getProductData($title: String!) {
  products(first: 1, query: $title) {
    edges {
      node {
        id
        title
        variants(first: 50) {
          edges {
            node {
              id
              title
              selectedOptions {
                name
                value
              }
              inventoryItem {
                id
                inventoryLevels(first: 50) { 
                  edges {
                    node {
                      location {
                        id
                      }
                      quantities(names: ["available"]) {
                        quantity
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# --- CORRECCIÓN v4 ---
# Mutación corregida para incluir 'reason', 'name' y usar 'delta' correctamente.
ADJUST_INVENTORY_MUTATION = """
mutation adjustInventory($inventoryItemID: ID!, $locationID: ID!, $delta: Int!) {
  inventoryAdjustQuantities(
    input: {
      reason: "correction"
      name: "available"
      changes: [
        {
          inventoryItemId: $inventoryItemID
          locationId: $locationID
          delta: $delta
        }
      ]
    }
  ) {
    inventoryAdjustmentGroup {
      id
    }
    userErrors {
      field
      message
    }
  }
}
"""
# --- FIN DE LA CORRECCIÓN ---


def update_stock(product_title, variant_option, new_stock):
    print(f"🔍 Iniciando actualización de stock (Modo GraphQL v4) para '{product_title}', variante '{variant_option}' a {new_stock} unidades.")
    
    try:
        # 1. Obtener la ubicación
        print("🏢 Paso 1: Obteniendo ubicación (GraphQL)...")
        location_data = run_shopify_query(GET_LOCATION_QUERY, {})
        if not location_data or not location_data['locations']['edges']:
            print("❌ No se encontraron ubicaciones. Abortando.")
            return
            
        location_node = location_data['locations']['edges'][0]['node']
        location_id = location_node['id']
        print(f"✅ Usando ubicación: {location_node['name']} (ID: {location_id})")

        # 2. Obtener el Producto y Variantes
        print("📦 Paso 2: Buscando producto y variantes (GraphQL)...")
        
        exact_title_query = f"title:'{product_title}'"
        print(f"   (Buscando con query exacto: {exact_title_query})")
        variables = {"title": exact_title_query} 
        
        product_data = run_shopify_query(GET_DATA_QUERY, variables)

        if not product_data or not product_data['products']['edges']:
            print(f"❌ Producto '{product_title}' no encontrado con búsqueda exacta.")
            return
        
        product_node = product_data['products']['edges'][0]['node']
        print(f"✅ Producto encontrado: {product_node['title']} (ID: {product_node['id']})")
        
        # 3. Buscar la variante específica
        print("🔍 Paso 3: Buscando variante específica y stock...")
        target_variant = None
        current_available = 0
        inventory_item_id = None
        
        variants = product_node['variants']['edges']
        for variant_edge in variants:
            variant = variant_edge['node']
            variant_title = variant.get('title', 'N/A')
            print(f"   Revisando variante: {variant_title}")

            variant_match = False
            
            if variant_option == variant_title:
                variant_match = True
            
            if not variant_match:
                for option in variant.get('selectedOptions', []):
                    if variant_option == option.get('value'):
                        variant_match = True
                        break

            if variant_match:
                target_variant = variant
                print(f"✅ Variante encontrada: {target_variant['title']} (ID: {target_variant['id']})")
                
                inventory_item_id = target_variant['inventoryItem']['id']
                print(f"   Inventory Item ID: {inventory_item_id}")
                
                inv_levels = target_variant['inventoryItem']['inventoryLevels']['edges']
                print(f"   Buscando stock para ubicación {location_id} entre {len(inv_levels)} niveles...")
                
                for level_edge in inv_levels:
                    level = level_edge['node']
                    if level['location']['id'] == location_id:
                        if level['quantities']:
                            current_available = level['quantities'][0]['quantity']
                        break 
                
                print(f"✅ Stock actual en Shopify: {current_available} unidades")
                break
        
        if not target_variant:
            print(f"❌ Variante '{variant_option}' no encontrada en el producto '{product_node['title']}'.")
            return

        # 4. Calcular el ajuste
        adjustment = new_stock - current_available
        print(f"🔢 Paso 4: Cálculo de ajuste: {new_stock} - {current_available} = {adjustment}")
        if adjustment == 0:
            print(f"ℹ️  El stock ya es {new_stock}. No se requiere ajuste.")
            return
        print(f"⚙️  Ajustando stock en {adjustment} unidades...")

        # 5. Ajustar el stock
        print("💾 Paso 5: Ajustando stock (GraphQL Mutation)...")
        mutation_variables = {
            "inventoryItemID": inventory_item_id,
            "locationID": location_id,
            "delta": adjustment
        }
        adjust_response = run_shopify_query(ADJUST_INVENTORY_MUTATION, mutation_variables)
        
        if adjust_response and (not adjust_response['inventoryAdjustQuantities'] or not adjust_response['inventoryAdjustQuantities']['userErrors']):
            print(f"✅ ¡Éxito! Stock actualizado a {new_stock} unidades para la variante '{variant_option}'.")
        else:
            print(f"❌ Error al ajustar stock. Respuesta: {adjust_response}")

    except Exception as e:
        print(f"❌ Error catastróficamente al actualizar el stock: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # Parámetros del test
    product_title = "Manteca de Karité"
    variant_option = "500 gr"
    new_stock = 6
    
    def timeout_handler(signum, frame):
        raise TimeoutError("La operación tardó demasiado tiempo (timeout de 30 segundos)")
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)
    
    try:
        update_stock(product_title, variant_option, new_stock)
    except TimeoutError as e:
        print(f"Error: {e}")
    finally:
        signal.alarm(0)