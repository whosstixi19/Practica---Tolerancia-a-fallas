#!/bin/bash

# Colores para la consola
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== INICIANDO AUTOMATIZACIÓN DE CAOS (INTEGRANTE 3) ===${NC}\n"

# 1. Verificar estado del clúster multi-nodo
echo -e "${GREEN}[1/5] Verificando nodos activos en Minikube...${NC}"
kubectl get nodes -o wide
echo ""

# 2. CAOS 1: El Inventario Fantasma (Caída de Pod)
echo -e "${RED}[CAOS 1] Provocando caída del Servicio de Inventario...${NC}"
POD_INV=$(kubectl get pods -l app=servicio-inventario -o jsonpath="{.items[0].metadata.name}" 2>/dev/null)
if [ -z "$POD_INV" ]; then
    echo -e "${RED}Error: No se encontró el pod de servicio-inventario.${NC}"
else
    echo "Eliminando pod de forma abrupta: $POD_INV"
    kubectl delete pod $POD_INV --now[cite: 3]
    echo -e "${GREEN}-> Ejecuta una reserva YA. Observa los RETRIES con Backoff Exponencial en los logs.${NC}\n"[cite: 3]
fi

# 3. CAOS 2: La Pasarela Lenta (Latencia Extrema)
echo -e "${RED}[CAOS 2] Activando latencia de 20s en el Servicio de Pagos...${NC}"[cite: 3]
# Inyectamos una variable de entorno al despliegue para activar el retraso en el stub
kubectl set env deployment/servicio-pagos-stub LATENCIA_ACTIVA=true[cite: 3]
echo -e "${GREEN}-> Ejecuta una reserva. La primera dará Timeout tras 3s; luego el Circuit Breaker pasará a ABIERTO y cortará en seco.${NC}\n"[cite: 3]

# Pausa para que realices la prueba en vivo antes de restaurar
read -p "Presiona [Enter] una vez que demuestres el Circuit Breaker para restaurar la pasarela..."

echo -e "${GREEN}[Restaurando] Removiendo latencia artificial de la Pasarela de Pagos...${NC}"
kubectl set env deployment/servicio-pagos-stub LATENCIA_ACTIVA-
echo ""

# 4. CAOS 3: El Correo Perdido (Fallo No Crítico)
echo -e "${RED}[CAOS 3] Simulando caída total del Servicio de Notificaciones...${NC}"[cite: 3]
kubectl scale deployment servicio-notificaciones --replicas=0[cite: 3]
echo -e "${GREEN}-> Ejecuta una reserva. Observa cómo la compra finaliza con éxito gracias al FALLBACK Silencioso.${NC}\n"[cite: 3]

read -p "Presiona [Enter] una vez que demuestres el Fallback para levantar el servicio de correos..."

echo -e "${GREEN}[Restaurando] Levantando de nuevo el Servicio de Notificaciones...${NC}"
kubectl scale deployment servicio-notificaciones --replicas=1[cite: 3]
echo ""

# 5. CAOS 4: El Diluvio de Peticiones (Prueba de Carga)
echo -e "${RED}[CAOS 4] Disparando el Diluvio de Peticiones masivas contra el API Gateway...${NC}"[cite: 3]
if command -v k6 &> /dev/null
then
    k6 run script-carga-k6.js[cite: 3]
else
    echo -e "${RED}[ERROR] k6 no está instalado localmente.${NC}"[cite: 3]
fi
echo -e "${GREEN}-> Observa las métricas de k6: el exceso de tráfico debe retornar código HTTP 429 (Too Many Requests).${NC}\n"[cite: 3]

echo -e "${GREEN}=== GUION DE CAOS Y RECUERACIÓN FINALIZADO ===${NC}"[cite: 3]