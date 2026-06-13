import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  AppBar, Toolbar, Typography, Box, TextField, Select, MenuItem,
  ButtonGroup, Button, Chip, CircularProgress, useMediaQuery,
} from '@mui/material';
import GridViewIcon from '@mui/icons-material/GridView';
import TableRowsIcon from '@mui/icons-material/TableRows';
import { fetchOrders } from '../api';
import OrderCard from '../components/OrderCard';
import OrderTable from '../components/OrderTable';

const LIMIT = 50;

export default function OrderList({ onOpenDetail }) {
  const [orders, setOrders] = useState([]);
  const [stats, setStats] = useState(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('created');
  const [view, setView] = useState(() => localStorage.getItem('orderView') || (window.innerWidth < 768 ? 'card' : 'table'));

  const isMobile = useMediaQuery('(max-width:600px)');
  const sentinelRef = useRef(null);

  const load = useCallback(async (pageNum, append) => {
    if (loading) return;
    setLoading(true);
    try {
      const data = await fetchOrders({ page: pageNum, limit: LIMIT, search, sort });
      if (append) {
        setOrders(prev => {
          const existing = new Set(prev.map(o => o.thread_id));
          return [...prev, ...data.orders.filter(o => !existing.has(o.thread_id))];
        });
      } else {
        setOrders(data.orders);
      }
      setTotal(data.total);
      setHasMore(pageNum < data.total_pages);
      if (data.stats) setStats(data.stats);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [loading, search, sort]);

  // Initial load + reload on search/sort change
  useEffect(() => {
    setOrders([]);
    setPage(1);
    setHasMore(true);
    load(1, false);
  }, [search, sort]); // eslint-disable-line

  // Infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !loading) {
        const next = page + 1;
        setPage(next);
        load(next, true);
      }
    }, { rootMargin: '200px' });
    if (sentinelRef.current) observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMore, loading, page, load]);

  const handleViewChange = (v) => {
    setView(v);
    localStorage.setItem('orderView', v);
  };

  return (
    <Box sx={{ pb: 4 }}>
      <AppBar position="sticky" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Toolbar variant="dense" sx={{ gap: 1, flexWrap: 'wrap', minHeight: 40 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mr: 1 }}>📋 Orders</Typography>
          <Button size="small" href="/" sx={{ fontSize: 11 }}>Saved Messages</Button>
          <Button size="small" href="/donhang" sx={{ fontSize: 11 }}>#don_hang</Button>
        </Toolbar>
        <Box sx={{ px: 1, pb: 0.5, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <TextField
            placeholder="Search customer, phone, product..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            fullWidth
            size="small"
            sx={{ '& .MuiOutlinedInput-root': { borderRadius: 1.5 } }}
          />
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Select value={sort} onChange={(e) => setSort(e.target.value)} size="small" sx={{ minWidth: 100, fontSize: 12 }}>
              <MenuItem value="created">Created</MenuItem>
              <MenuItem value="updated">Updated</MenuItem>
              <MenuItem value="date">Invoice Date</MenuItem>
            </Select>
            <ButtonGroup size="small">
              <Button variant={view === 'card' ? 'contained' : 'outlined'} onClick={() => handleViewChange('card')}>
                <GridViewIcon fontSize="small" />
              </Button>
              <Button variant={view === 'table' ? 'contained' : 'outlined'} onClick={() => handleViewChange('table')}>
                <TableRowsIcon fontSize="small" />
              </Button>
            </ButtonGroup>
          </Box>
        </Box>
        {stats && (
          <Box sx={{ px: 1, pb: 0.5, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Chip label={`${stats.total_orders?.toLocaleString('vi-VN')} total`} size="small" variant="outlined" />
            <Chip label={`${stats.pending?.toLocaleString('vi-VN')} pending`} size="small" color="warning" />
            <Chip label={`${stats.done?.toLocaleString('vi-VN')} done`} size="small" color="success" />
          </Box>
        )}
        <Typography variant="caption" sx={{ px: 1, pb: 0.5, color: 'text.secondary' }}>
          {orders.length} of {total?.toLocaleString('vi-VN')}
        </Typography>
      </AppBar>

      <Box sx={{ p: 0.5 }}>
        {view === 'card' ? (
          <Box sx={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 0.5,
          }}>
            {orders.map(o => (
              <OrderCard key={o.thread_id} order={o} onClick={() => onOpenDetail(o.thread_id)} />
            ))}
          </Box>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <OrderTable orders={orders} onRowClick={(id) => onOpenDetail(id)} />
          </Box>
        )}
        <Box ref={sentinelRef} sx={{ textAlign: 'center', py: 2 }}>
          {loading && <CircularProgress size={24} />}
          {!loading && hasMore && <Typography variant="caption" color="text.secondary">Scroll for more...</Typography>}
          {!hasMore && orders.length > 0 && <Typography variant="caption" color="text.secondary">✅ All loaded</Typography>}
        </Box>
      </Box>
    </Box>
  );
}
