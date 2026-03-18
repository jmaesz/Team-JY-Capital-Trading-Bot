import { cn } from "../../lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "success" | "danger" | "warning";
}

const variants = {
  default: "bg-muted text-muted-foreground",
  success: "bg-emerald-500/15 text-emerald-400",
  danger:  "bg-red-500/15 text-red-400",
  warning: "bg-yellow-500/15 text-yellow-400",
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}
