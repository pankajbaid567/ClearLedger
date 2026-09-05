import { Download } from "lucide-react";

export function ExportButton({
  href,
  label,
  testId,
}: {
  href: string;
  label: string;
  testId?: string;
}) {
  return (
    <a className="btn btn-secondary" data-testid={testId} download href={href}>
      <Download aria-hidden="true" size={15} />
      {label}
    </a>
  );
}

