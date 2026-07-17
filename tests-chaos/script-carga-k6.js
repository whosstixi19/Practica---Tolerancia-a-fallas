import http from 'k6/http';
import { sleep, check } from 'k6';

// Configuración de la ráfaga de caos: 50 usuarios atacando en paralelo por 10 segundos
export const options = {
  vus: 50,
  duration: '10s',
};

export default function () {
  // Dirección local donde el API Gateway estará expuesto en la demo
  const url = 'http://localhost:8000/api/v1/reservas'; 
  
  const payload = JSON.stringify({
    evento_id: 'evento_1',
    cantidad: 1,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(url, payload, params);
  
  // Verificamos que responda con éxito (200) o que se active tu Rate Limiter controlado (429)
  check(res, {
    'Respuesta HTTP normal (200) o Bloqueo controlado (429)': (r) => r.status === 200 || r.status === 429,
  });
  
  // Intervalo de ráfaga muy corto (100ms por usuario) para forzar el diluvio de peticiones
  sleep(0.1); 
}