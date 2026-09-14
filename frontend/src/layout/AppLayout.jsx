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
}) {
  const sidebarButtonRef = useRef(null);
  const sidebarCloseRef = useRef(null);
  const railExpandRef = useRef(null);
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

  useEffect(() => {
    if (!isMobile && desktopCollapsed) railExpandRef.current?.focus();
  }, [isMobile, desktopCollapsed]);

  const toggleSidebar = () => {
    if (isMobile) {
      if (mobileOpen) closeMobileSidebar();
      else setMobileOpen(true);
    } else {
      setDesktopCollapsed((current) => !current);
    }
  };

  return (
    <div className="app-shell">
      {isMobile && mobileOpen && <button className="sidebar-scrim" aria-label="Close sidebar" onClick={closeMobileSidebar} />}
      <Sidebar
        open={mobileOpen}
        collapsed={!isMobile && desktopCollapsed}
        isMobile={isMobile}
        onClose={closeMobileSidebar}
        closeButtonRef={sidebarCloseRef}
        railExpandRef={railExpandRef}
        onCollapse={toggleSidebar}
        onNewChat={onNewChat}
        conversations={conversations}
        onSelectConversation={onSelectConversation}
        onDeleteConversation={onDeleteConversation}
        onRenameConversation={onRenameConversation}
        userName={userName}
      />
      <main className="workspace-main" inert={isMobile && mobileOpen}>
        {isMobile && <button ref={sidebarButtonRef} className="mobile-sidebar-trigger" type="button" aria-label="Open sidebar" aria-expanded={mobileOpen} onClick={toggleSidebar}><PanelLeft size={19} strokeWidth={1.7} /></button>}
        <div className="workspace-content">{children}</div>
      </main>
    </div>
  );
}
