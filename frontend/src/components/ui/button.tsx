import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Every variant is at least 56px tall (`tap`). The `accent` variant is the
 * single "press this" affordance — never show two of them on one screen.
 */
const button = cva(
  "tap inline-flex items-center justify-center gap-3 rounded-2xl font-semibold " +
    "transition-[transform,background-color,box-shadow] duration-150 " +
    "active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
  {
    variants: {
      variant: {
        accent:
          "bg-accent text-white shadow-lg shadow-accent/25 hover:bg-accent/90",
        brand: "bg-brand text-white shadow-md shadow-brand/20 hover:bg-brand/90",
        outline:
          "border-2 border-line bg-surface text-ink hover:border-brand hover:bg-brand-soft",
        ghost: "text-ink-soft hover:bg-surface-sunk hover:text-ink",
        danger: "bg-danger text-white hover:bg-danger/90",
      },
      size: {
        md: "px-6 text-base",
        lg: "px-8 py-5 text-lg",
        icon: "aspect-square w-14 px-0",
      },
    },
    defaultVariants: { variant: "brand", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(button({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
