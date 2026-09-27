import { useTheme } from "../../hooks/useTheme";

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button type="button" className="theme-toggle" onClick={toggleTheme}>
      {theme === "dark" ? "☀ Chế độ sáng" : "🌙 Chế độ tối"}
    </button>
  );
}
