import { MvpOfficialScheduleFrame } from "@/components/MvpOfficialScheduleFrame";

type Props = { params: Promise<{ meetKey: string }> };

export default async function OfficialScheduleRoute({ params }: Props) {
  const { meetKey: raw } = await params;
  const meetKey = decodeURIComponent(raw);
  return (
    <main className="min-h-dvh">
      <MvpOfficialScheduleFrame meetKey={meetKey} />
    </main>
  );
}
