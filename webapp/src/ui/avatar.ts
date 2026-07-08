// Màu avatar ỔN ĐỊNH theo tên (hash) — nhận diện người/khách nhanh trong list dài.
// Dùng chung: TasksBoard (avatar người làm), Customers (avatar khách).
const AVA_COLORS = ["#1a73e8", "#188038", "#b26b00", "#7b3ff2", "#c2185b", "#00838f"];

export const avaColor = (s: string) =>
  AVA_COLORS[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % AVA_COLORS.length];
