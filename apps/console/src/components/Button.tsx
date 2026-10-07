import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Base = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  /** Shown as the tooltip when the button is disabled, so a disabled action always says why. */
  disabledReason?: string;
};
/** A button either has visible text, or it is icon-only and MUST carry an aria-label and a tooltip. */
type Props = Base & ({ children: ReactNode; iconLabel?: undefined } | { children: ReactNode; iconLabel: string });

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = "secondary", size = "md", className = "", disabledReason, iconLabel, title, type, ...rest },
  ref,
) {
  const cls = ["btn", variant === "primary" ? "btn-primary" : variant === "ghost" ? "btn-ghost" : "", size === "sm" ? "btn-sm" : "", className]
    .filter(Boolean)
    .join(" ");
  const tip = rest.disabled && disabledReason ? disabledReason : title ?? iconLabel;
  return <button ref={ref} type={type ?? "button"} className={cls} title={tip} aria-label={iconLabel} {...rest} />;
});
