import React, { useState, useEffect } from 'react';
import {
  AppBar, Toolbar, Typography, Box, Card, CardContent, Table, TableHead, TableBody,
  TableRow, TableCell, CircularProgress, Link, Accordion, AccordionSummary, AccordionDetails,
  Chip,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { fetchOrder } from '../api';

function fmtVND(val) {
  if (!val && val !== 0) return '—';
  const n = typeof val === 'string' ? parseInt(val.replace(/\./g, '')) : parseInt(val);
  if (isNaN(n) || n === 0) return '—';
  return n.toLocaleString('vi-VN') + '₫';
}

function toVnTime(utcStr) {
  if (!utcStr) return '';
  const m = utcStr.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/);
  if (!m) return utcStr;
  let h = +m[4] + 7, d = +m[3], mo = +m[2] - 1, y = +m[1];
  if (h >= 24) { h -= 24; d++; }
  return `${String(h).padStart(2, '0')}:${m[5]} ${String(d).padStart(2, '0')}/${String(mo + 1).padStart(2, '0')}`;
}

function Row({ label, value }) {
  return (
    <Box sx={{ display: 'flex', py: 0.25 }}>
      <Typography variant="body2" sx={{ width: 120, color: 'text.secondary', flexShrink: 0, fontSize: 12 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ flex: 1, wordBreak: 'break-word', fontSize: 12 }}>
        {value}
      </Typography>
    </Box>
  );
}

const TASK_TYPES = ['ban_hd', 'soan_hang', 'giao_hang', 'nop_tien', 'nhan_tien'];
const TASK_LABELS = { ban_hd: 'Bán HĐ', soan_hang: 'Soạn hàng', giao_hang: 'Giao hàng', nop_tien: 'Nộp tiền', nhan_tien: 'Nhận tiền' };

export default function OrderDetail({ threadId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    fetchOrder(threadId)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [threadId]);

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress /></Box>;
  if (error) return <Typography color="error" sx={{ p: 2 }}>❌ {error.message}</Typography>;
  if (!data) return null;

  const d = data.data || data;
  const hd = d.hoadon || {};
  const pc = hd.print_content || {};
  const tasks = d.task_status || {};
  const invoice = d.invoice || d.invoice_items || [];
  const payments = d.payments || [];
  const chatMessages = data.chat_messages || [];

  const userName = {};
  chatMessages.forEach(m => { if (m.sender_id && m.sender_name) userName[String(m.sender_id)] = m.sender_name; });
  const showName = (id) => {
    if (!id) return '';
    if (Array.isArray(id)) return id.map(x => userName[String(x)] || x).join(', ');
    return userName[String(id)] || String(id);
  };

  const customer = d.customer_name || pc.kh || d.customer || d.khach_hang || '—';
  const hdCode = d.hd_code || hd.hd_code || d.kiotvietInvoiceCode || '';
  const phone = d.phone || pc.sdt || d.so_dien_thoai || '—';
  const date = d.date || pc.datetime || '';
  const total = d.total || pc.tongthanhtoan || '';
  const text = d.text || d.text_raw || '';
  const key = d.key || d.firebase_key || '';
  const channelId = String(d.channel_id || data.channel_id || '').replace('-100', '');
  const msgId = d.message_id || data.message_id || '';

  return (
    <Box sx={{ pb: 4 }}>
      <AppBar position="sticky" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Toolbar variant="dense" sx={{ minHeight: 40, gap: 1 }}>
          <Link component="button" onClick={onBack} sx={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <ArrowBackIcon fontSize="small" /> Back
          </Link>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, flex: 1 }}>
            Order {hdCode || '#' + (d.thread_id || threadId)} — {customer}
          </Typography>
        </Toolbar>
      </AppBar>

      <Box sx={{ px: 0.5, pt: 0.5, display: 'flex', flexDirection: 'column', gap: 0.5, maxWidth: 800, mx: 'auto' }}>
        {/* Basic Info */}
        <Card>
          <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
            <Typography variant="overline" sx={{ color: 'text.secondary', fontSize: 10 }}>Basic Info</Typography>
            <Row label="Thread ID" value={d.thread_id || threadId} />
            <Row label="Customer" value={customer} />
            <Row label="Phone" value={phone} />
            <Row label="Total" value={fmtVND(total)} />
            <Row label="Date" value={date || '—'} />
            <Row label="HD Code" value={hdCode || '—'} />
            <Row label="Firebase Key" value={key || '—'} />
            <Row label="Creator" value={showName(d.nguoi_tao_HD) || '—'} />
            {channelId && msgId && (
              <Row label="Telegram" value={
                <Link href={`https://t.me/c/${channelId}/${msgId}`} target="_blank">Open in Telegram ↗</Link>
              } />
            )}
          </CardContent>
        </Card>

        {/* Order Text */}
        {text && (
          <Card>
            <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
              <Typography variant="overline" sx={{ color: 'text.secondary', fontSize: 10 }}>Order Text</Typography>
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mt: 0.25, fontSize: 12 }}>
                {text}
              </Typography>
            </CardContent>
          </Card>
        )}

        {/* Chat Messages */}
        {chatMessages.length > 0 && (
          <Card>
            <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
              <Typography variant="overline" sx={{ color: 'text.secondary', fontSize: 10 }}>Chat Messages ({chatMessages.length})</Typography>
              {chatMessages.map((m, i) => (
                <Box key={i} sx={{ py: 0.25, borderBottom: i < chatMessages.length - 1 ? 1 : 0, borderColor: 'divider' }}>
                  <Typography variant="caption" color="text.secondary">
                    {toVnTime(m.created_at)} <strong>{m.sender_name || m.sender_id || '?'}</strong>
                  </Typography>
                  <Typography variant="body2" sx={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
                    {m.text || (m.media_type ? `[${m.media_type}]` : '—')}
                  </Typography>
                </Box>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Task Status */}
        <Card>
          <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
            <Typography variant="overline" sx={{ color: 'text.secondary', fontSize: 10 }}>Task Status</Typography>
            {TASK_TYPES.map(tt => {
              const st = tasks[tt];
              const done = st && st.done;
              return (
                <Row
                  key={tt}
                  label={TASK_LABELS[tt]}
                  value={
                    done ? (
                      <Typography component="span" variant="body2" sx={{ color: 'success.main', fontSize: 12 }}>
                        ✅ Done{st.skip ? ' (skipped)' : ''}{st.note ? ' — ' + st.note : ''}{st.by ? ' — ' + showName(st.by) : ''}
                      </Typography>
                    ) : (
                      <Typography component="span" variant="body2" sx={{ color: 'text.disabled', fontSize: 12 }}>
                        ❌ Not done
                      </Typography>
                    )
                  }
                />
              );
            })}
          </CardContent>
        </Card>

        {/* Invoice Items */}
        {invoice.length > 0 && (
          <Card>
            <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
              <Typography variant="overline" sx={{ color: 'text.secondary', fontSize: 10 }}>Invoice Items ({invoice.length})</Typography>
              <Table size="small" sx={{ mt: 0.5 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Product</TableCell>
                    <TableCell align="right">Qty</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Total</TableCell>
                    <TableCell>Note</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {invoice.map((item, i) => {
                    const qty = item.sl || item.quantity || item.sl1pc || 0;
                    const price = item.price || 0;
                    const itemTotal = qty * price;
                    return (
                      <TableRow key={i}>
                        <TableCell>{item.sp || item.productCode || item.name || '?'}</TableCell>
                        <TableCell align="right">{qty}</TableCell>
                        <TableCell align="right">{fmtVND(price)}</TableCell>
                        <TableCell align="right">{fmtVND(itemTotal)}</TableCell>
                        <TableCell>{item.note || item.qc_type || '—'}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Payments */}
        {payments.length > 0 && (
          <Card>
            <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
              <Typography variant="overline" sx={{ color: 'text.secondary', fontSize: 10 }}>Payments ({payments.length})</Typography>
              {payments.map((p, i) => (
                <Row key={i} label={`${p.method || '?'} ${p.created_at ? p.created_at.slice(0, 10) : ''}`} value={fmtVND(p.amount)} />
              ))}
            </CardContent>
          </Card>
        )}

        {/* Raw JSON */}
        <Accordion disableGutters elevation={0} sx={{ border: 1, borderColor: 'divider' }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="overline" sx={{ fontSize: 10 }}>Raw JSON</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Box component="pre" sx={{ fontSize: 11, overflow: 'auto', maxHeight: 300, m: 0 }}>
              {JSON.stringify(d, null, 2)}
            </Box>
          </AccordionDetails>
        </Accordion>
      </Box>
    </Box>
  );
}
