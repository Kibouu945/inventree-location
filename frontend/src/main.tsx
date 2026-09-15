import React from 'react';
import ReactDOM from 'react-dom/client';

function App() {
  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
      <h1>InvenTree Location - Dev Server</h1>
      <p>
        Ce serveur Vite sert au développement du frontend du plugin. Les
        composants sont chargés par InvenTree sur{' '}
        <a href='http://localhost:8000'>http://localhost:8000</a>.
      </p>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
