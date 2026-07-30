import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-teal-600 text-white shadow-sm hover:bg-teal-700 active:scale-[0.98]",
        secondary: "bg-teal-50 text-teal-700 hover:bg-teal-100 border border-teal-100",
        outline: "border border-line bg-surface text-ink hover:bg-paper-dim",
        ghost: "text-ink-soft hover:bg-paper-dim hover:text-ink",
        link: "text-teal-700 underline-offset-4 hover:underline",
        destructive: "bg-danger text-white hover:bg-danger/90",
      },
      size: {
        default: "h-10 px-5 py-2",
        sm: "h-8 px-4 text-[13px]",
        lg: "h-12 px-7 text-base",
        icon: "h-9 w-9 rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
