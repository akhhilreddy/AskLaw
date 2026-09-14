import { Scale } from "lucide-react";
import { Link } from "react-router-dom";
export default function Logo({ to = "/" }) { return <Link className="brand" to={to} aria-label="AskLAW home"><span className="brand-mark"><Scale size={21} strokeWidth={1.8}/></span><span>AskLAW</span></Link>; }
