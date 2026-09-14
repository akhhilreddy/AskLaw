import { FileText, History, MessageSquareText, PanelLeftOpen, Plus, Scale, UserRound } from "lucide-react";
import { NavLink } from "react-router-dom";

export default function SidebarRail({ expandRef, onExpand, onNewChat, onClose, showRecent, userName }) {
  return (
    <div className="sidebar-rail">
      <button ref={expandRef} type="button" className="rail-brand-toggle" aria-label="Expand sidebar" title="Expand sidebar" onClick={onExpand}>
        <span className="brand-mark rail-brand-icon"><Scale size={21} strokeWidth={1.8} /></span>
        <PanelLeftOpen className="rail-expand-icon" size={20} strokeWidth={1.7} />
      </button>
      <nav className="rail-navigation" aria-label="Workspace navigation">
        <button type="button" aria-label="New chat" title="New chat" onClick={onNewChat}><Plus size={19} /></button>
        <NavLink to="/dashboard" onClick={onClose} aria-label="Chat" title="Chat" className={({ isActive }) => isActive ? "active" : ""}><MessageSquareText size={19} /></NavLink>
        <NavLink to="/documents" onClick={onClose} aria-label="Documents" title="Documents" className={({ isActive }) => isActive ? "active" : ""}><FileText size={19} /></NavLink>
        {showRecent && <button type="button" aria-label="Recent chats" title="Recent chats" onClick={onExpand}><History size={19} /></button>}
      </nav>
      <button type="button" className="rail-account" aria-label={`${userName || "Account"} — expand account controls`} title={`${userName || "Account"} — expand account controls`} onClick={onExpand}><UserRound size={19} /></button>
    </div>
  );
}
