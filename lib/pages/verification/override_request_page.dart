import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/override_request.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:provider/provider.dart';

/// Override petugas setelah biometrik gagal berulang.
///
/// Alur sengaja berat: dua petugas berbeda harus hadir dan login, alasan dipilih
/// dari daftar tertutup, dan bukti fisik dicatat. Kalau override lebih mudah
/// daripada verifikasi normal, ia berhenti menjadi pengaman dan berubah menjadi
/// jalur fraud - rute termudah selalu yang paling sering dipakai.
class OverrideRequestPage extends StatefulWidget {
  const OverrideRequestPage({
    super.key,
    required this.sessionId,
    required this.sessionToken,
  });

  final String sessionId;
  final String sessionToken;

  @override
  State<OverrideRequestPage> createState() => _OverrideRequestPageState();
}

class _OverrideRequestPageState extends State<OverrideRequestPage> {
  final _noteController = TextEditingController();

  OverrideReason? _reason;
  StaffSession? _petugas;
  StaffSession? _supervisor;
  bool _busy = false;
  String? _error;
  String? _result;
  bool _requested = false;

  @override
  void dispose() {
    _noteController.dispose();
    super.dispose();
  }

  VerificationApiService get _api => context.read<VerificationApiService>();

  Future<void> _login({required bool asSupervisor}) async {
    final session = await showDialog<StaffSession>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _StaffLoginDialog(
        title: asSupervisor ? 'Login Supervisor' : 'Login Petugas',
        requireSupervisor: asSupervisor,
      ),
    );
    if (session == null || !mounted) return;

    // Empat mata. Server memeriksa ini terhadap data tersimpan, bukan terhadap
    // klaim klien - pemeriksaan di sini hanya agar petugas tahu lebih awal.
    if (asSupervisor && _petugas?.staffId == session.staffId) {
      setState(() => _error =
          'Supervisor harus orang yang berbeda dari petugas pengaju.');
      return;
    }

    setState(() {
      _error = null;
      if (asSupervisor) {
        _supervisor = session;
      } else {
        _petugas = session;
      }
    });
  }

  Future<void> _submitRequest() async {
    final petugas = _petugas;
    final reason = _reason;
    if (petugas == null || reason == null) return;

    if (reason.requiresNote && _noteController.text.trim().length < 10) {
      setState(() => _error =
          "Alasan 'Lainnya' wajib dijelaskan minimal 10 karakter.");
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });

    final result = await _api.requestOverride(
      sessionId: widget.sessionId,
      sessionToken: widget.sessionToken,
      staffToken: petugas.token,
      reason: reason,
      note: _noteController.text.trim(),
    );

    if (!mounted) return;
    result.when(
      ok: (_) => setState(() {
        _busy = false;
        _requested = true;
      }),
      failure: (f) => setState(() {
        _busy = false;
        _error = f.message;
      }),
    );
  }

  Future<void> _approve() async {
    final supervisor = _supervisor;
    if (supervisor == null) return;

    setState(() {
      _busy = true;
      _error = null;
    });

    final result = await _api.approveOverride(
      sessionId: widget.sessionId,
      sessionToken: widget.sessionToken,
      supervisorToken: supervisor.token,
      note: _noteController.text.trim(),
    );

    if (!mounted) return;
    result.when(
      ok: (body) {
        setState(() {
          _busy = false;
          _result = body['decision'] as String?;
        });
        // Hasil dikembalikan ke alur utama supaya layar hasil bisa menampilkan
        // nomor bukti dan sinyal risiko yang menyertai override.
        Navigator.of(context).pop(body);
      },
      failure: (f) => setState(() {
        _busy = false;
        _error = f.message;
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Override Petugas')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _banner(),
            const SizedBox(height: 20),
            _stepCard(
              index: 1,
              title: 'Petugas pengaju',
              done: _petugas != null,
              child: _petugas == null
                  ? OutlinedButton.icon(
                      onPressed: _busy ? null : () => _login(asSupervisor: false),
                      icon: const Icon(Icons.badge_outlined),
                      label: const Text('Login Petugas'),
                    )
                  : Text('${_petugas!.nama} (${_petugas!.role})',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
            ),
            const SizedBox(height: 12),
            _stepCard(
              index: 2,
              title: 'Alasan override',
              done: _reason != null,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // RadioGroup, bukan groupValue per tile: yang terakhir sudah
                  // deprecated sejak Flutter 3.32.
                  RadioGroup<OverrideReason>(
                    groupValue: _reason,
                    // onChanged is non-nullable here, so the locked state is
                    // enforced inside rather than by passing null.
                    onChanged: (value) {
                      if (_requested || _busy) return;
                      setState(() => _reason = value);
                    },
                    child: Column(
                      children: OverrideReason.values
                          .map(
                            (r) => RadioListTile<OverrideReason>(
                              value: r,
                              dense: true,
                              contentPadding: EdgeInsets.zero,
                              title: Text(r.label,
                                  style: const TextStyle(fontSize: 13)),
                            ),
                          )
                          .toList(),
                    ),
                  ),
                  if (_reason?.requiresNote ?? false)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: TextField(
                        controller: _noteController,
                        enabled: !_requested && !_busy,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Penjelasan (wajib, min. 10 karakter)',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _stepCard(
              index: 3,
              title: 'Ajukan ke supervisor',
              done: _requested,
              child: _requested
                  ? const Text('Permohonan terkirim. Menunggu persetujuan.',
                      style: TextStyle(fontSize: 13))
                  : FilledButton(
                      onPressed: (_petugas == null || _reason == null || _busy)
                          ? null
                          : _submitRequest,
                      child: const Text('Ajukan Override'),
                    ),
            ),
            const SizedBox(height: 12),
            _stepCard(
              index: 4,
              title: 'Persetujuan supervisor',
              done: _result != null,
              enabled: _requested,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_supervisor == null)
                    OutlinedButton.icon(
                      onPressed: (!_requested || _busy)
                          ? null
                          : () => _login(asSupervisor: true),
                      icon: const Icon(Icons.verified_user_outlined),
                      label: const Text('Login Supervisor'),
                    )
                  else ...[
                    Text('${_supervisor!.nama} (${_supervisor!.role})',
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 10),
                    FilledButton.icon(
                      onPressed: _busy ? null : _approve,
                      icon: const Icon(Icons.check),
                      label: const Text('Setujui Override'),
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF34A853),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFD93025).withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline,
                        color: Color(0xFFD93025), size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                        child: Text(_error!,
                            style: const TextStyle(fontSize: 13))),
                  ],
                ),
              ),
            ],
            if (_busy) ...[
              const SizedBox(height: 16),
              const Center(child: CircularProgressIndicator()),
            ],
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _banner() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF9AB00).withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFF9AB00).withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.warning_amber_rounded,
                  color: Color(0xFFE8710A), size: 20),
              SizedBox(width: 8),
              Expanded(
                child: Text('Override dicatat permanen',
                    style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Layar ini untuk petugas faskes - serahkan ponsel ke petugas. '
            'Klaim yang disetujui lewat override ditandai '
            'APPROVED_WITH_OVERRIDE, bukan APPROVED, dan otomatis masuk '
            'antrean tinjauan BPJS. Frekuensi override per petugas dipantau.',
            style: TextStyle(fontSize: 12, color: Colors.grey.shade800),
          ),
        ],
      ),
    );
  }

  Widget _stepCard({
    required int index,
    required String title,
    required Widget child,
    bool done = false,
    bool enabled = true,
  }) {
    final theme = Theme.of(context);
    return Opacity(
      opacity: enabled ? 1 : 0.45,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: done
                ? const Color(0xFF34A853).withValues(alpha: 0.5)
                : Colors.grey.shade200,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: done
                        ? const Color(0xFF34A853)
                        : theme.colorScheme.primary.withValues(alpha: 0.12),
                  ),
                  child: Center(
                    child: done
                        ? const Icon(Icons.check, size: 14, color: Colors.white)
                        : Text('$index',
                            style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: theme.colorScheme.primary)),
                  ),
                ),
                const SizedBox(width: 10),
                Text(title,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 14)),
              ],
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

class _StaffLoginDialog extends StatefulWidget {
  const _StaffLoginDialog({required this.title, required this.requireSupervisor});

  final String title;
  final bool requireSupervisor;

  @override
  State<_StaffLoginDialog> createState() => _StaffLoginDialogState();
}

class _StaffLoginDialogState extends State<_StaffLoginDialog> {
  final _nip = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _nip.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final result = await context.read<VerificationApiService>().staffLogin(
          nip: _nip.text.trim(),
          password: _password.text,
        );
    if (!mounted) return;
    result.when(
      ok: (session) {
        if (widget.requireSupervisor && !session.isSupervisor) {
          setState(() {
            _busy = false;
            _error = 'Akun ini bukan supervisor.';
          });
          return;
        }
        Navigator.of(context).pop(session);
      },
      failure: (f) => setState(() {
        _busy = false;
        _error = f.message;
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _nip,
            autofocus: true,
            decoration: const InputDecoration(
              labelText: 'NIP',
              prefixIcon: Icon(Icons.badge_outlined),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _password,
            obscureText: true,
            onSubmitted: (_) => _submit(),
            decoration: const InputDecoration(
              labelText: 'Kata sandi',
              prefixIcon: Icon(Icons.lock_outline),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!,
                style: const TextStyle(color: Color(0xFFD93025), fontSize: 13)),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Batal'),
        ),
        FilledButton(
          onPressed: _busy ? null : _submit,
          child: _busy
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.white),
                )
              : const Text('Masuk'),
        ),
      ],
    );
  }
}
