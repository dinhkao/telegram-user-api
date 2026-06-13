import React from 'react';
import { Card, CardActionArea, CardContent, Typography, Box, Chip } from '@mui/material';

function fmtVND(val) {
  if (!val) return null;
  return parseInt(String(val).replace(/\./g, '')).toLocaleString('vi-VN') + '₫';
}

function relativeTime(dateStr) {
  if (!dateStr) return '';
  const m = dateStr.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})/);
  if (!m) return '';
  const then = new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5]);
  const diffMin = Math.floor((Date.now() - then) / 60000);
  if (diffMin < 1) return 'Vừa xong';
  if (diffMin < 60) return diffMin + ' phút';
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return diffH + ' giờ';
  const diffD = Math.floor(diffH / 24);
  if (diffD === 1) return 'Hôm qua';
  if (diffD < 7) return diffD + ' ngày';
  if (diffD < 30) return Math.floor(diffD / 7) + ' tuần';
  return Math.floor(diffD / 30) + ' tháng';
}

function debtInfo(o) {
  const rawTotal = o.total ? parseInt(String(o.total).replace(/\./g, '')) : 0;
  if (o.nhan_tien_note === 'gtr') return { text: 'Gửi toa rồi', color: 'warning.main' };
  if (rawTotal > 0 && o.remaining === 0) return { text: '✅', color: 'success.main' };
  if (rawTotal > 0 && o.paid > 0) return { text: o.remaining.toLocaleString('vi-VN') + '₫', color: 'warning.main' };
  if (rawTotal > 0) return { text: o.remaining.toLocaleString('vi-VN') + '₫', color: 'error.main' };
  return null;
}

export default function OrderCard({ order: o, onClick }) {
  const total = fmtVND(o.total);
  const debt = debtInfo(o);
  const rel = relativeTime(o.date);
  const invItems = o.invoice_summary || [];
  const steps = ['soan', 'giao', 'nop', 'nhan'];
  const stepLabels = { soan: 'Soạn', giao: 'Giao', nop: 'Nộp', nhan: 'Nhận' };

  return (
    <Card sx={{ '&:hover': { boxShadow: 3 } }}>
      <CardActionArea onClick={onClick} sx={{ p: 1 }}>
        <CardContent sx={{ p: 0, '&:last-child': { pb: 0 } }}>
          {/* Order text */}
          <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.4, mb: 0.25, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {o.text || o.customer || '—'}
          </Typography>

          {/* Customer + meta */}
          <Typography variant="caption" color="text.secondary">
            {o.customer || '—'}
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.25 }}>
            {o.hd_code && <Typography variant="caption" color="text.disabled">{o.hd_code}</Typography>}
            {o.date && <Typography variant="caption" color="text.disabled">{o.date}</Typography>}
            {rel && <Typography variant="caption" color="warning.main" fontWeight={500}>{rel} trước</Typography>}
          </Box>

          {/* Total + Debt */}
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 0.5 }}>
            {total && <Typography variant="subtitle2" fontWeight={700}>{total}</Typography>}
            {debt && <Typography variant="body2" fontWeight={600} color={debt.color}>{debt.text}</Typography>}
          </Box>

          {/* Invoice items */}
          {invItems.length > 0 && (
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.25 }}>
              {invItems.map((it, i) => (
                <Chip key={i} label={`${it.sp} x${it.sl}`} size="small" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
              ))}
              {o.invoice_count > invItems.length && (
                <Typography variant="caption" color="text.disabled">+{o.invoice_count - invItems.length} more</Typography>
              )}
            </Box>
          )}

          {/* Steps */}
          <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
            {steps.map(s => (
              <Chip
                key={s}
                label={stepLabels[s]}
                size="small"
                variant="filled"
                color={o[s] ? 'success' : 'default'}
                sx={{ fontSize: 10, height: 20, fontWeight: o[s] ? 600 : 400 }}
              />
            ))}
          </Box>

          {/* Footer */}
          <Typography variant="caption" color="text.disabled" sx={{ mt: 0.25, display: 'block' }}>
            #{o.thread_id}
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
