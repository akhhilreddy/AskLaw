import { Copy,Check } from "lucide-react";
import { useState } from "react";
export default function MessageActions({content}){const [copied,setCopied]=useState(false);const handleCopy=async()=>{try{await navigator.clipboard.writeText(content);setCopied(true);setTimeout(()=>setCopied(false),2000)}catch(error){console.error("Could not copy answer:",error)}};return <div className="message-actions"><button type="button" onClick={handleCopy} aria-label={copied?"Answer copied":"Copy answer"}>{copied?<Check size={14}/>:<Copy size={14}/>} {copied?"Copied":"Copy answer"}</button></div>}
