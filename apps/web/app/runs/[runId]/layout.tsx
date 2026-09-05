import { RunShell } from "@/components/RunShell";

export default async function RunLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <RunShell runId={runId}>{children}</RunShell>;
}

