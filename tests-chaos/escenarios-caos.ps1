Write-Host "=== INICIANDO AUTOMATIZACION DE CAOS (INTEGRANTE 3) ===" -ForegroundColor Green

Write-Host "[1/5] Verificando nodos activos en Minikube..." -ForegroundColor Green
minikube kubectl -- get nodes -o wide

Write-Host "[CAOS 1] Provocando caida del Servicio de Inventario..." -ForegroundColor Red
$POD_INV = (minikube kubectl -- get pods -l app=servicio-inventario -o jsonpath="{.items[0].metadata.name}" 2>$null)
if (-not $POD_INV) {
    Write-Host "Error: No se encontro el pod de servicio-inventario." -ForegroundColor Red
} else {
    Write-Host "Eliminando pod de forma abrupta: $POD_INV"
    minikube kubectl -- delete pod $POD_INV --now
    Write-Host "-> Ejecuta una reserva YA. Observa los RETRIES con Backoff Exponencial en los logs." -ForegroundColor Green
}

Write-Host "[CAOS 2] Activando latencia de 20s en el Servicio de Pagos..." -ForegroundColor Red
minikube kubectl -- set env deployment/servicio-pagos-stub LATENCIA_ACTIVA=true
Write-Host "-> Ejecuta una reserva. La primera dara Timeout tras 3s; luego el Circuit Breaker pasara a ABIERTO y cortara en seco." -ForegroundColor Green

Read-Host "Presiona [Enter] una vez que demuestres el Circuit Breaker para restaurar la pasarela..."

Write-Host "[Restaurando] Removiendo latencia artificial de la Pasarela de Pagos..." -ForegroundColor Green
minikube kubectl -- set env deployment/servicio-pagos-stub LATENCIA_ACTIVA-

Write-Host "[CAOS 3] Simulando caida total del Servicio de Notificaciones..." -ForegroundColor Red
minikube kubectl -- scale deployment servicio-notificaciones --replicas=0
Write-Host "-> Ejecuta una reserva. Observa como la compra finaliza con exito gracias al FALLBACK Silencioso." -ForegroundColor Green

Read-Host "Presiona [Enter] una vez que demuestres el Fallback para levantar el servicio de correos..."

Write-Host "[Restaurando] Levantando de nuevo el Servicio de Notificaciones..." -ForegroundColor Green
minikube kubectl -- scale deployment servicio-notificaciones --replicas=1

Write-Host "[CAOS 4] Disparando el Diluvio de Peticiones masivas contra el API Gateway..." -ForegroundColor Red
if (Get-Command k6 -ErrorAction SilentlyContinue) {
    k6 run "$PSScriptRoot\script-carga-k6.js"
} else {
    Write-Host "[ERROR] k6 no esta instalado localmente." -ForegroundColor Red
}
Write-Host "-> Observa las metricas de k6: el exceso de trafico debe retornar codigo HTTP 429 (Too Many Requests)." -ForegroundColor Green

Write-Host "=== GUION DE CAOS Y RECUPERACION FINALIZADO ===" -ForegroundColor Green