import {
  ShieldCheck,
  Zap,
  BrainCircuit,
} from "lucide-react";

const features = [
  {
    icon: ShieldCheck,
    title: "Secure Conversations",
    description:
      "Your legal queries stay private and protected.",
  },
  {
    icon: Zap,
    title: "Lightning Fast",
    description:
      "Get instant AI-powered legal assistance.",
  },
  {
    icon: BrainCircuit,
    title: "Intelligent Research",
    description:
      "Built to understand legal documents and legal questions.",
  },
];

function FeatureList() {
  return (
    <div className="mt-12 space-y-6">
      {features.map((feature) => {
        const Icon = feature.icon;

        return (
          <div
            key={feature.title}
            className="
            flex
            gap-4
            rounded-2xl
            border
            border-white/5
            bg-white/5
            p-5
            transition-all
            duration-300
            hover:bg-white/10
            hover:translate-x-2
            "
          >
            <div className="rounded-xl bg-blue-600/10 p-3">
              <Icon
                className="text-blue-500"
                size={24}
              />
            </div>

            <div>
              <h3 className="font-semibold text-white">
                {feature.title}
              </h3>

              <p className="mt-1 text-sm text-zinc-400">
                {feature.description}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default FeatureList;