import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function IconBase({ size = 18, children, ...props }: IconProps) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>{children}</svg>;
}

export const HomeIcon = (props: IconProps) => <IconBase {...props}><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></IconBase>;
export const JobsIcon = (props: IconProps) => <IconBase {...props}><rect x="3" y="5" width="18" height="15" rx="2"/><path d="M8 5V3h8v2M3 11h18M10 14h4"/></IconBase>;
export const PlusIcon = (props: IconProps) => <IconBase {...props}><path d="M12 5v14M5 12h14"/></IconBase>;
export const ContractIcon = (props: IconProps) => <IconBase {...props}><path d="M7 3h10l3 3v15H4V3h3"/><path d="M8 8h8M8 12h8M8 16h5"/></IconBase>;
export const SunIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/></IconBase>;
export const MoonIcon = (props: IconProps) => <IconBase {...props}><path d="M20.5 14.2A8.3 8.3 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z"/></IconBase>;
export const ArrowIcon = (props: IconProps) => <IconBase {...props}><path d="M5 12h14M13 6l6 6-6 6"/></IconBase>;
export const ExternalIcon = (props: IconProps) => <IconBase {...props}><path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v7H4V6h7"/></IconBase>;
export const ShieldIcon = (props: IconProps) => <IconBase {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></IconBase>;
export const SparkIcon = (props: IconProps) => <IconBase {...props}><path d="m12 3 1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Z"/><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z"/></IconBase>;
export const RefreshIcon = (props: IconProps) => <IconBase {...props}><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 8A7 7 0 0 1 18 6l2 6M18 16a7 7 0 0 1-11.9 2L4 12"/></IconBase>;
export const WalletIcon = (props: IconProps) => <IconBase {...props}><path d="M3 6h15a3 3 0 0 1 3 3v9H3V6Z"/><path d="M3 6V4h14v2M16 11h5v4h-5a2 2 0 0 1 0-4Z"/></IconBase>;
export const CheckIcon = (props: IconProps) => <IconBase {...props}><path d="m5 12 4 4L19 6"/></IconBase>;
export const ClockIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></IconBase>;
export const AlertIcon = (props: IconProps) => <IconBase {...props}><path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v4M12 17h.01"/></IconBase>;
export const MenuIcon = (props: IconProps) => <IconBase {...props}><path d="M4 7h16M4 12h16M4 17h16"/></IconBase>;
export const CloseIcon = (props: IconProps) => <IconBase {...props}><path d="m6 6 12 12M18 6 6 18"/></IconBase>;
export const LockIcon = (props: IconProps) => <IconBase {...props}><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></IconBase>;
export const UserIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></IconBase>;
export const FileIcon = (props: IconProps) => <IconBase {...props}><path d="M6 2h8l4 4v16H6Z"/><path d="M14 2v5h5M9 13h6M9 17h4"/></IconBase>;
export const LinkIcon = (props: IconProps) => <IconBase {...props}><path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1"/></IconBase>;
export const CopyIcon = (props: IconProps) => <IconBase {...props}><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></IconBase>;
export const CodeIcon = (props: IconProps) => <IconBase {...props}><path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/></IconBase>;
export const ChevronIcon = (props: IconProps) => <IconBase {...props}><path d="m9 18 6-6-6-6"/></IconBase>;
export const ActivityIcon = (props: IconProps) => <IconBase {...props}><path d="M3 12h4l2-6 4 12 2-6h6"/></IconBase>;
