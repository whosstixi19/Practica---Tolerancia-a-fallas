#!/bin/bash
# reset-demo.sh — Resetea estado de Circuit Breakers entre escenarios de caos
# Uso: bash reset-demo.sh
# Ejecutar desde PC1 (tixilegion)

set -e

echo "[RESET] Reiniciando servicio-reservas para limpiar estado de breakers..."
sudo kubectl rollout restart deployment/servicio-reservas
echo "[RESET] Esperando que el nuevo pod esté Running..."
sudo kubectl rollout status deployment/servicio-reservas --timeout=60s
echo "[RESET] OK — Breakers reiniciados. Sistema listo."
sudo kubectl get pods -l app=servicio-reservas
