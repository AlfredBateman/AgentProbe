import type { SVGProps } from "react";

// A handful of 16px stroke icons; not worth an icon dependency. Square caps and mitred joins,
// to match the square corners everywhere else.
function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="square"
      strokeLinejoin="miter"
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
export const CopyIcon = (p: P) => <Icon {...p}><path d="M5.5 5.5h8v8h-8zM10.5 5.5v-3h-8v8h3" /></Icon>;
export const CheckIcon = (p: P) => <Icon {...p}><path d="M3 8.5l3 3 7-7" /></Icon>;
export const ChevronDownIcon = (p: P) => <Icon {...p}><path d="M4 6l4 4 4-4" /></Icon>;
export const PlusIcon = (p: P) => <Icon {...p}><path d="M8 3v10M3 8h10" /></Icon>;
export const MinusIcon = (p: P) => <Icon {...p}><path d="M3 8h10" /></Icon>;
export const ArrowUpRightIcon =(p: P) => <Icon {...p}><path d="M4 12L12 4M6 4h6v6" /></Icon>;
export const SortIcon = ({ direction, ...p }: P & { direction?: "ascending" | "descending" }) => (
  <Icon {...p}>
    <path d="M5 6.5L8 3.5l3 3" opacity={direction === "descending" ? 0.3 : 1} />
    <path d="M5 9.5l3 3 3-3" opacity={direction === "ascending" ? 0.3 : 1} />
  </Icon>
);
