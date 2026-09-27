import type { SVGProps } from "react";

// A handful of 16px stroke icons; not worth an icon dependency.
function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    >
      {children}
    </svg>
  );
}

type P = SVGProps<SVGSVGElement>;
export const MenuIcon = (p: P) => <Icon {...p}><path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" /></Icon>;
export const CloseIcon = (p: P) => <Icon {...p}><path d="M4 4l8 8M12 4l-8 8" /></Icon>;
export const CopyIcon = (p: P) => <Icon {...p}><rect x="5.5" y="5.5" width="8" height="8" rx="1.5" /><path d="M10.5 5.5V3.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2" /></Icon>;
export const CheckIcon = (p: P) => <Icon {...p}><path d="M3 8.5l3 3 7-7" /></Icon>;
export const ChevronDownIcon = (p: P) => <Icon {...p}><path d="M4 6l4 4 4-4" /></Icon>;
export const SortIcon = ({ direction, ...p }: P & { direction?: "ascending" | "descending" }) => (
  <Icon {...p}>
    <path d="M5 6.5L8 3.5l3 3" opacity={direction === "descending" ? 0.3 : 1} />
    <path d="M5 9.5l3 3 3-3" opacity={direction === "ascending" ? 0.3 : 1} />
  </Icon>
);
