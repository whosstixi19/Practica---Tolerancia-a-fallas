import http from 'k6/http';
import { sleep, check } from 'k6';

export const options = {
  vus: 50,
  duration: '10s',
};

export default function () {
  const baseUrl = __ENV.URL || 'http://localhost:8000/api/v1/comprar'; 

  const payload = JSON.stringify({
    evento_id: 'evento_1',
    cantidad: 1,
    usuario_email: 'jose.tixi@est.ups.edu.ec' 
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(baseUrl, payload, params);
  
  check(res, {
    'Respuesta normal (200) o Bloqueo Rate Limit (429)': (r) => r.status === 200 || r.status === 429,
  });
  
  sleep(0.1); 
}
