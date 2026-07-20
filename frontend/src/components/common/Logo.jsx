import { Scale } from "lucide-react";

function Logo() {
  return (
    <div className="mb-10 flex justify-center">
      <div className="flex items-center gap-2">
        <Scale size={24} />
        <span className="text-3xl font-semibold tracking-tight">
          AskLaw
        </span>
      </div>
    </div>
  );
}

export default Logo;