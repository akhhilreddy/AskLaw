import AppRoutes from "./routes/AppRoutes";
import ServerReadiness from "./components/common/ServerReadiness";

function App() {
  return <><ServerReadiness /><AppRoutes /></>;
}

export default App;
