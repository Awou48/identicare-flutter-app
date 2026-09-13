import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/verification_session.dart';
import 'package:identicare_mobile/state/verification_flow_controller.dart';
import 'package:identicare_mobile/widgets/verification/data_review_tile.dart';
import 'package:identicare_mobile/widgets/verification/status_badge.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

/// Langkah 3 - Periksa Ulang Data.
///
/// Ini titik pertama alur yang menampilkan data peserta sebenarnya, dan hanya
/// setelah KEDUA faktor biometrik lolos. Sebelum itu server hanya mengirim versi
/// bertopeng, supaya menebak nomor BPJS tidak bisa membocorkan data siapa pun.
class Step3ReviewDataPage extends StatefulWidget {
  const Step3ReviewDataPage({super.key});

  @override
  State<Step3ReviewDataPage> createState() => _Step3ReviewDataPageState();
}

class _Step3ReviewDataPageState extends State<Step3ReviewDataPage> {
  bool _confirmed = false;
  bool _requested = false;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<VerificationFlowController>();

    // Data baru diambil ketika langkah ini benar-benar aktif: IndexedStack
    // membangun semua anaknya, jadi build() ini juga berjalan saat pengguna
    // masih di langkah 1. Tanpa pemeriksaan currentStep, permintaan review
    // ditembakkan ke sesi yang masih 'created', server menjawab 409
    // STEP_OUT_OF_ORDER, dan pesannya muncul di layar scan wajah sebagai
    // "Langkah verifikasi tidak berurutan" - tanpa pengguna berbuat apa pun.
    final active = controller.currentStep == SessionStep.review;
    if (active && !_requested && controller.reviewData == null && !controller.isBusy) {
      _requested = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => controller.loadReview());
    }

    final data = controller.reviewData;
    if (data == null) {
      return Center(
        child: controller.error != null
            ? Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline, size: 48, color: Color(0xFFD93025)),
                    const SizedBox(height: 12),
                    Text(controller.error!, textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: () {
                        controller.clearError();
                        controller.loadReview();
                      },
                      child: const Text('Coba Lagi'),
                    ),
                  ],
                ),
              )
            : const CircularProgressIndicator(),
      );
    }

    final peserta = data.peserta;
    final claim = data.claim;
    final currency = NumberFormat.currency(locale: 'id_ID', symbol: 'Rp ', decimalDigits: 0);
    final wajahScore = (data.wajah['score'] as num?)?.toDouble();
    final securityLevel = data.sidikJari['security_level'] as String?;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Periksa kembali data Anda',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(
            'Pastikan seluruh data benar sebelum klaim diverifikasi.',
            style: TextStyle(color: Colors.grey.shade700, fontSize: 13),
          ),
          const SizedBox(height: 20),

          _Section(
            title: 'Data Peserta',
            trailing: StatusBadge(
              status: peserta.isAktif ? 'APPROVED' : 'REJECTED',
              compact: true,
            ),
            children: [
              DataReviewTile(
                label: 'Nama',
                value: peserta.namaLengkap,
                icon: Icons.person_outline,
                highlight: true,
              ),
              DataReviewTile(
                label: 'Nomor BPJS',
                value: peserta.noBpjs,
                icon: Icons.badge_outlined,
                monospace: true,
              ),
              DataReviewTile(
                label: 'NIK',
                value: peserta.nikMasked,
                icon: Icons.credit_card_outlined,
                monospace: true,
              ),
              if (peserta.tanggalLahir != null)
                DataReviewTile(
                  label: 'Tanggal Lahir',
                  value: DateFormat('dd MMMM yyyy', 'id_ID').format(peserta.tanggalLahir!),
                  icon: Icons.cake_outlined,
                ),
              DataReviewTile(
                label: 'Jenis Kelamin',
                value: peserta.jenisKelaminLabel,
                icon: Icons.wc_outlined,
              ),
              DataReviewTile(
                label: 'Kelas Rawat',
                value: peserta.kelasRawat == null ? '-' : 'Kelas ${peserta.kelasRawat}',
                icon: Icons.bed_outlined,
              ),
              DataReviewTile(
                label: 'Jenis Peserta',
                value: peserta.jenisPeserta ?? '-',
                icon: Icons.groups_outlined,
              ),
              DataReviewTile(
                label: 'Status',
                value: peserta.statusKepesertaan +
                    (peserta.tunggakanBulan > 0
                        ? ' (${peserta.tunggakanBulan} bulan menunggak)'
                        : ''),
                icon: Icons.verified_user_outlined,
              ),
              if (peserta.faskesTingkat1 != null)
                DataReviewTile(
                  label: 'Faskes Tk. 1',
                  value: peserta.faskesTingkat1!,
                  icon: Icons.local_hospital_outlined,
                ),
            ],
          ),
          const SizedBox(height: 16),

          _Section(
            title: 'Detail Klaim',
            children: [
              DataReviewTile(
                label: 'Jenis Layanan',
                value: claim.jenisLayananLabel,
                icon: Icons.medical_services_outlined,
              ),
              DataReviewTile(label: 'Poli', value: claim.poli, icon: Icons.meeting_room_outlined),
              DataReviewTile(
                label: 'Fasilitas',
                value: claim.faskes,
                icon: Icons.location_on_outlined,
              ),
              DataReviewTile(
                label: 'Estimasi Biaya',
                value: currency.format(claim.estimasiBiaya),
                icon: Icons.payments_outlined,
              ),
            ],
          ),
          const SizedBox(height: 16),

          _Section(
            title: 'Hasil Biometrik',
            children: [
              BiometricResultCard(
                title: 'Verifikasi Wajah',
                passed: data.wajah['passed'] == true,
                icon: Icons.face_retouching_natural,
                detail: wajahScore != null
                    ? 'Skor kecocokan ${wajahScore.toStringAsFixed(3)}'
                    : null,
              ),
              const SizedBox(height: 8),
              BiometricResultCard(
                title: 'Verifikasi Sidik Jari',
                passed: data.sidikJari['passed'] == true,
                icon: Icons.fingerprint,
                detail: securityLevel == null ? null : 'Tingkat keamanan: $securityLevel',
                // Ditampilkan apa adanya, bukan disamarkan: jalur HMAC tidak
                // terikat perangkat keras dan itu memang menaikkan skor risiko.
                warning: securityLevel == 'SOFTWARE'
                    ? 'Belum terikat perangkat keras (TEE). Skor risiko naik.'
                    : null,
              ),
            ],
          ),
          const SizedBox(height: 24),

          CheckboxListTile(
            value: _confirmed,
            onChanged: (value) => setState(() => _confirmed = value ?? false),
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            title: const Text(
              'Saya menyatakan data di atas benar dan klaim ini diajukan oleh '
              'saya sendiri.',
              style: TextStyle(fontSize: 13),
            ),
          ),
          const SizedBox(height: 8),

          if (controller.error != null) ...[
            Text(
              controller.error!,
              style: const TextStyle(color: Color(0xFFD93025), fontSize: 13),
            ),
            const SizedBox(height: 12),
          ],

          FilledButton(
            onPressed: (!_confirmed || controller.isBusy)
                ? null
                : () => controller.confirmReview(),
            style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
            child: controller.isBusy
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Text('Konfirmasi & Lanjutkan'),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.children, this.trailing});

  final String title;
  final List<Widget> children;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
              if (trailing != null) trailing!,
            ],
          ),
          const Divider(height: 20),
          ...children,
        ],
      ),
    );
  }
}
