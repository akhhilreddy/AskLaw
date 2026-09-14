import { useEffect, useRef, useState } from "react";
import { PanelLeft } from "lucide-react";
import Sidebar from "../components/dashboard/Sidebar";

export default function AppLayout({
  children,
  onNewChat,
  conversations,
  onSelectConversation,
  onDeleteConversation,
  onRenameConversation,
  userName,
  section = "Chat",
  title,
}) {
  const sidebarButtonRef = useRef(null);
  const sidebarCloseRef = useRef(null);
  const hadMobileDrawerRef = useRef(false);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia("(max-width: 700px)").matches);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 700px)");
    const handleChange = (event) => {
      setIsMobile(event.matches);
      setMobileOpen(false);
    };
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, []);

  const closeMobileSidebar = () => {
    setMobileOpen(false);
  };

  useEffect(() => {
    if (isMobile && mobileOpen) hadMobileDrawerRef.current = true;
    else if (isMobile && hadMobileDrawerRef.current) {
      sidebarButtonRef.current?.focus();
      hadMobileDrawerRef.current = false;
    }
  }, [isMobile, mobileOpen]);

  useEffect(() => {
    if (!isMobile || !mobileOpen) return;
    sidebarCloseRef.current?.focus();
    const onEscape = (event) => {
      if (event.key === "Escape") closeMobileSidebar();
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [isMobile, mobileOpen]);

  const toggleSidebar = () => {
    if (isMobile) {
      if (mobileOpen) closeMobileSidebar();
      else setMobileOpen(true);
    } else {
      if (!desktopCollapsed) sidebarButtonRef.current?.focus();
      setDesktopCollapsed((current) => !current);
    }
  };
  const sidebarExpanded = isMobile ? mobileOpen : !desktopCollapsed;
  const headerTitle = title || (section === "Chat" ? "" : section);

  return (
    <div className="app-shell">
      {isMobile && mobileOpen && <button className="sidebar-scrim" aria-label="Close sidebar" onClick={closeMobileSidebar} />}
      <Sidebar
        open={mobileOpen}
        collapsed={!isMobile && desktopCollapsed}
        isMobile={isMobile}
        onClose={closeMobileSidebar}
        closeButtonRef={sidebarCloseRef}
        onCollapse={toggleSidebar}
        onNewChat={onNewChat}
        conversations={conversations}
        onSelectConversation={onSelectConversation}
        onDeleteConversation={onDeleteConversation}
        onRenameConversation={onRenameConversation}
        userName={userName}
      />
      <main className="workspace-main" inert={isMobile && mobileOpen}>
        <header className="workspace-topbar">
          <div className="topbar-kicker">
            <button ref={sidebarButtonRef} className="sidebar-toggle" type="button" aria-label={sidebarExpanded ? (isMobile ? "Close sidebar" : "Collapse sidebar") : "Open sidebar"} aria-expanded={sidebarExpanded} onClick={toggleSidebar}>
              <PanelLeft size={19} strokeWidth={1.7} />
            </button>
            {headerTitle && <span className="topbar-title" title={headerTitle}>{headerTitle}</span>}
          </div>
        </header>
        <div className="workspace-content">{children}</div>
      </main>
    </div>
  );
}
