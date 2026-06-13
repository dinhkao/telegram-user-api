import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1565c0' },
    background: { default: '#f0f2f5' },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: '"Roboto", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    fontSize: 13,
  },
  components: {
    MuiCard: {
      defaultProps: { elevation: 1 },
      styleOverrides: { root: { borderRadius: 8 } },
    },
    MuiButton: {
      styleOverrides: { root: { textTransform: 'none', borderRadius: 6 } },
    },
    MuiTextField: {
      defaultProps: { size: 'small', variant: 'outlined' },
    },
    MuiSelect: {
      defaultProps: { size: 'small' },
    },
    MuiTableCell: {
      styleOverrides: { root: { padding: '4px 8px', fontSize: 12 } },
    },
    MuiTableHead: {
      styleOverrides: { root: { '& th': { fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.3 } } },
    },
  },
});

export default theme;
