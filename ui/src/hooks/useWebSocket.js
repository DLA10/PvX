import React, { useState, useEffect } from 'react';

const useWebSocket = (url) => {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('disconnected');

  useEffect(() => {
    const ws = new WebSocket(url);

    ws.onopen = () => setStatus('connected');
    ws.onmessage = (event) => setData(JSON.parse(event.data));
    ws.onclose = () => setStatus('disconnected');

    return () => ws.close();
  }, [url]);

  return { data, status };
};

export default useWebSocket;
