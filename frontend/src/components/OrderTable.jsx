import React from 'react';
import { Table, TableHead, TableBody, TableRow, TableCell, Typography, Link } from '@mui/material';

function fmtVND(val) {
  if (!val) return '—';
  return parseInt(String(val).replace(/\./g, '')).toLocaleString('vi-VN') + '₫';
}

function debtInfo(o) {
  const rawTotal = o.total ? parseInt(String(o.total).replace(/\./g, '')) : 0;
  if (o.nhan_tien_note === 'gtr') return { text: 'Gửi toa rồi', color: 'warning.main' };
  if (rawTotal > 0 && o.remaining === 0) return { text: '✅', color: 'success.main' };
  if (rawTotal > 0 && o.paid > 0) return { text: o.remaining.toLocaleString('vi-VN') + '₫', color: 'warning.main' };
  if (rawTotal > 0) return { text: o.remaining.toLocaleString('vi-VN') + '₫', color: 'error.main' };
  return { text: '—', color: 'text.disabled' };
}

const STEPS = ['soan', 'giao', 'nop', 'nhan'];
const STEP_LABELS = { soan: 'Soạn', giao: 'Giao', nop: 'Nộp', nhan: 'Nhận' };

export default function OrderTable({ orders, onRowClick }) {
  return (
    <Table size="small" sx={{ minWidth: 700 }}>
      <TableHead>
        <TableRow>
          <TableCell>Thread</TableCell>
          <TableCell>HD Code</TableCell>
          <TableCell>Customer</TableCell>
          <TableCell align="right">Total</TableCell>
          <TableCell align="right">Debt</TableCell>
          <TableCell>Steps</TableCell>
          <TableCell>Date</TableCell>
          <TableCell>Creator</TableCell>
          <TableCell align="right">Items</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {orders.map(o => {
          const debt = debtInfo(o);
          const tgChannel = String(o.channel_id || '').replace('-100', '');
          return (
            <TableRow
              key={o.thread_id}
              hover
              onClick={() => onRowClick(o.thread_id)}
              sx={{ cursor: 'pointer' }}
            >
              <TableCell>
                {tgChannel && o.message_id ? (
                  <Link
                    href={`https://t.me/c/${tgChannel}/${o.message_id}`}
                    target="_blank"
                    onClick={(e) => e.stopPropagation()}
                    sx={{ fontSize: 12 }}
                  >
                    {o.thread_id}
                  </Link>
                ) : o.thread_id}
              </TableCell>
              <TableCell>{o.hd_code || '—'}</TableCell>
              <TableCell>{o.customer || '—'}</TableCell>
              <TableCell align="right" sx={{ fontFamily: 'monospace' }}>{fmtVND(o.total)}</TableCell>
              <TableCell align="right" sx={{ fontFamily: 'monospace', color: debt.color, fontWeight: 600 }}>
                {debt.text}
              </TableCell>
              <TableCell>
                <Typography component="span" variant="caption" sx={{ display: 'flex', gap: 0.5 }}>
                  {STEPS.map(s => (
                    <Typography
                      key={s}
                      component="span"
                      variant="caption"
                      sx={{ color: o[s] ? 'success.main' : 'text.disabled', fontWeight: o[s] ? 600 : 400 }}
                    >
                      {STEP_LABELS[s]}
                    </Typography>
                  ))}
                </Typography>
              </TableCell>
              <TableCell>{o.date || '—'}</TableCell>
              <TableCell>{o.creator || '—'}</TableCell>
              <TableCell align="right">{o.invoice_count || 0}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
