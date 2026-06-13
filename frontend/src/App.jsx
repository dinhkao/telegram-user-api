import React, { useState, useEffect } from 'react';
import { ThemeProvider, CssBaseline } from '@mui/material';
import theme from './theme';
import OrderList from './pages/OrderList';
import OrderDetail from './pages/OrderDetail';

export default function App() {
  const [route, setRoute] = useState(() => {
    const path = window.location.pathname;
    const m = path.match(/^\/orders\/(\d+)/);
    if (m) return { page: 'detail', threadId: m[1] };
    return { page: 'list' };
  });

  useEffect(() => {
    const onPop = () => {
      const path = window.location.pathname;
      const m = path.match(/^\/orders\/(\d+)/);
      if (m) setRoute({ page: 'detail', threadId: m[1] });
      else setRoute({ page: 'list' });
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = (page, threadId) => {
    const url = page === 'detail' ? `/orders/${threadId}` : '/orders';
    window.history.pushState({}, '', url);
    setRoute({ page, threadId });
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {route.page === 'list' && <OrderList onOpenDetail={(id) => navigate('detail', id)} />}
      {route.page === 'detail' && <OrderDetail threadId={route.threadId} onBack={() => navigate('list')} />}
    </ThemeProvider>
  );
}
