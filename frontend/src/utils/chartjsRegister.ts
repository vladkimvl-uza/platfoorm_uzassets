/**
 * Chart.js explicit-registration shim.
 *
 * Replaces `import { Chart } from "chart.js/auto"` (which pulls ALL
 * controllers/scales/plugins ≈ 200KB) with cherry-picked imports of only
 * the chart types actually used:
 *   • doughnut   (Dashboard rings, CreditDonut — единый донат)
 *   • bar        (PaTornado, MaturityChart, CompanyFinCard, ForensicAudit, PaymentsCalendarBars)
 *   • line       (CompanyFinCard sparkline)
 *   • radar      (PaRadar — procurement radar)
 *   • bubble     (RiskBubbleChart — credit portfolio bubble scatter)
 *
 * Import this anywhere instead of "chart.js/auto":
 *   import { Chart } from "@/utils/chartjsRegister";
 */
import {
  Chart,
  BarController,
  BarElement,
  DoughnutController,
  ArcElement,
  LineController,
  LineElement,
  PointElement,
  RadarController,
  RadialLinearScale,
  BubbleController,
  CategoryScale,
  LinearScale,
  Filler,
  Tooltip,
  Legend,
  Title,
  type ChartConfiguration,
} from "chart.js";

Chart.register(
  // Controllers
  BarController,
  DoughnutController,
  LineController,
  RadarController,
  BubbleController,
  // Elements
  BarElement,
  ArcElement,
  LineElement,
  PointElement,
  // Scales
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  // Plugins
  Filler,
  Tooltip,
  Legend,
  Title,
);

export { Chart, type ChartConfiguration };
