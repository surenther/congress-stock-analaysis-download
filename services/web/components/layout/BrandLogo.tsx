import React from "react";
import { cn } from "@/lib/utils";

export type LogoVariant = "dual" | "spark" | "surge" | "candlestick";

interface BrandLogoIconProps extends React.SVGProps<SVGSVGElement> {
  variant?: LogoVariant;
  className?: string;
}

export function BrandLogoIcon({
  variant = "dual",
  className = "h-6 w-6",
  ...props
}: BrandLogoIconProps) {
  switch (variant) {
    case "surge":
      return (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.3"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={className}
          {...props}
        >
          <path d="M17 7C17 4.8 15 3 12 3C8.5 3 6.5 5 6.5 7.5C6.5 11 17.5 10.5 17.5 15.5C17.5 18.5 15 21 11.5 21C8 21 6.5 19 6.5 17" />
          <path d="M19 4.5L17 2.5L15 4.5" strokeWidth="1.8" />
        </svg>
      );
    case "candlestick":
      return (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={className}
          {...props}
        >
          <path d="M16.5 6.5H9.5C7.5 6.5 6 7.8 6 9.5C6 11.2 7.5 12.5 9.5 12.5H14.5C16.5 12.5 18 13.8 18 15.5C18 17.2 16.5 18.5 14.5 18.5H7" />
          <path d="M12 3v3.5m0 12V21" strokeWidth="1.8" opacity="0.75" />
        </svg>
      );
    case "spark":
      return (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={className}
          {...props}
        >
          <path d="M16 6.5C15 4.5 13.2 3.5 10.5 3.5C7.2 3.5 5.5 5.2 5.5 7.8C5.5 11.2 17 10.8 17 15.5C17 18.8 14.5 20.5 10.8 20.5C7.5 20.5 5.8 18.8 5.5 16.5" />
          <path d="M19 3v3m1.5-1.5h-3" strokeWidth="1.8" />
        </svg>
      );
    case "dual":
    default:
      return (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.3"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={className}
          {...props}
        >
          {/* Dual Chambers Interlock: House (top) & Senate (bottom) forming an 'S' */}
          <path d="M17.5 6C16 4 14 3 11.5 3C8 3 6.5 5 6.5 7.5C6.5 10.5 9.5 11.8 12 12.2" />
          <path d="M6.5 18C8 20 10 21 12.5 21C16 21 17.5 19 17.5 16.5C17.5 13.5 14.5 12.2 12 11.8" />
          {/* Central Surveillance Nexus */}
          <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
        </svg>
      );
  }
}

interface BrandBadgeProps {
  size?: "sm" | "md" | "lg";
  variant?: LogoVariant;
  className?: string;
}

export function BrandBadge({
  size = "md",
  variant = "dual",
  className,
}: BrandBadgeProps) {
  const containerSizes = {
    sm: "h-8 w-8 rounded-lg",
    md: "h-9 w-9 rounded-lg",
    lg: "h-12 w-12 rounded-xl",
  };

  const iconSizes = {
    sm: "h-4 w-4",
    md: "h-5 w-5",
    lg: "h-6 w-6",
  };

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.15)]",
        containerSizes[size],
        className
      )}
    >
      <BrandLogoIcon variant={variant} className={iconSizes[size]} />
    </div>
  );
}
