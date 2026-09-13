import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';
import 'package:identicare_mobile/pages/symptom_checker_page.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, required this.doctor});

  final Map<String, dynamic> doctor;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final _focusNode = FocusNode();

  bool _sending = false;
  bool _botTyping = false;
  Timer? _typingTimer;

  String get _doctorName => '${widget.doctor['name']}';
  String get _uid => context.read<AuthService>().currentUser?.uid ?? 'anon';
  String get _threadId {
    final uid = context.read<AuthService>().currentUser?.uid ?? 'anon';
    final slug =
        _doctorName.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-');
    return '${uid}_$slug';
  }

  @override
  void dispose() {
    _typingTimer?.cancel();
    _controller.dispose();
    _scrollController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  CollectionReference<Map<String, dynamic>> get _messages =>
      FirebaseFirestore.instance
          .collection('konsultasi_chat')
          .doc(_threadId)
          .collection('messages');

  Future<void> _send({String? preset}) async {
    final text = (preset ?? _controller.text).trim();
    if (text.isEmpty || _sending) return;

    final user = context.read<AuthService>().currentUser;
    if (user == null) return;

    setState(() => _sending = true);
    _controller.clear();

    try {
      await _messages.add({
        'userId': user.uid,
        'text': text,
        'sender': 'user',
        'timestamp': FieldValue.serverTimestamp(),
      });
      _scrollToBottom();
      _scheduleAutoReply(text);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Pesan gagal terkirim: $e'),
            backgroundColor: AppColors.danger,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _scheduleAutoReply(String userText) {
    _typingTimer?.cancel();
    setState(() => _botTyping = true);

    _typingTimer = Timer(const Duration(milliseconds: 1400), () async {
      if (!mounted) return;
      final user = context.read<AuthService>().currentUser;
      if (user == null) return;

      try {
        await _messages.add({
          'userId': user.uid,
          'text': _autoReply(userText),
          'sender': 'bot',
          'timestamp': FieldValue.serverTimestamp(),
        });
      } catch (_) {}
      if (mounted) {
        setState(() => _botTyping = false);
        _scrollToBottom();
      }
    });
  }

  String _autoReply(String text) {
    final lower = text.toLowerCase();

    const urgent = [
      'nyeri dada',
      'sesak',
      'tidak sadar',
      'pingsan',
      'kejang',
      'pendarahan',
      'darah',
      'stroke',
      'lumpuh',
    ];
    if (urgent.any(lower.contains)) {
      return 'Keluhan yang Anda sebutkan dapat menandakan kondisi gawat darurat. '
          'Segera kunjungi IGD terdekat atau hubungi 119. Jangan menunggu balasan '
          'di aplikasi ini.\n\n(Balasan otomatis)';
    }
    if (lower.contains('bpjs') ||
        lower.contains('klaim') ||
        lower.contains('verifikasi')) {
      return 'Untuk pertanyaan seputar verifikasi klaim BPJS, Anda dapat melihat '
          'riwayat verifikasi di tab Aktivitas, atau membaca artikel di beranda.\n\n'
          '(Balasan otomatis)';
    }
    if (lower.contains('demam') ||
        lower.contains('batuk') ||
        lower.contains('pilek')) {
      return 'Terima kasih. Untuk gejala seperti ini, Anda bisa mencoba fitur '
          'Cek Gejala agar mendapat gambaran awal sebelum konsultasi.\n\n'
          '(Balasan otomatis)';
    }
    if (lower.contains('jadwal') || lower.contains('janji')) {
      return 'Penjadwalan janji temu dapat dilihat di tab Jadwal.\n\n(Balasan otomatis)';
    }
    return 'Pesan Anda sudah tercatat. $_doctorName belum terhubung ke sistem '
        'konsultasi, jadi belum ada dokter yang membacanya. Untuk keluhan yang '
        'mendesak, silakan datang langsung ke fasilitas kesehatan.\n\n'
        '(Balasan otomatis)';
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent + 120,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Row(
          children: [
            CircleAvatar(
              radius: 17,
              backgroundColor: AppColors.brandSoft,
              child: Text(
                _doctorName
                    .replaceAll(RegExp(r'^Dr\.?\s*'), '')
                    .substring(0, 1)
                    .toUpperCase(),
                style: const TextStyle(
                  color: AppColors.brandDark,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    _doctorName,
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w600),
                  ),
                  Text(
                    '${widget.doctor['specialty']}',
                    style: const TextStyle(
                        fontSize: 11.5, color: AppColors.ink500),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          const _AutoReplyNotice(),
          Expanded(child: _messageList()),
          if (_botTyping) const _TypingIndicator(),
          _Composer(
            controller: _controller,
            focusNode: _focusNode,
            sending: _sending,
            onSend: _send,
            onQuickAction: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const SymptomCheckerPage()),
            ),
          ),
        ],
      ),
    );
  }

  Widget _messageList() {
    return StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
      stream: _messages
          .where('userId', isEqualTo: _uid)
          .orderBy('timestamp', descending: false)
          .snapshots(),
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return AppEmptyState(
            icon: Icons.error_outline_rounded,
            title: 'Tidak dapat memuat percakapan',
            message: 'Terjadi kesalahan saat membaca pesan dari Firestore.',
            detail: snapshot.error.toString(),
          );
        }
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        final docs = snapshot.data?.docs ?? const [];
        if (docs.isEmpty) {
          return _EmptyConversation(
            doctorName: _doctorName,
            onSuggestion: (text) => _send(preset: text),
          );
        }

        return ListView.builder(
          controller: _scrollController,
          padding: const EdgeInsets.all(AppSpacing.lg),
          itemCount: docs.length,
          itemBuilder: (context, index) {
            final data = docs[index].data();
            final isUser = data['sender'] == 'user';
            final timestamp = (data['timestamp'] as Timestamp?)?.toDate();

            final previous = index == 0 ? null : docs[index - 1].data();
            final previousDate =
                (previous?['timestamp'] as Timestamp?)?.toDate();
            final showDate = timestamp != null &&
                (previousDate == null || previousDate.day != timestamp.day);

            return Column(
              children: [
                if (showDate) _DateSeparator(date: timestamp),
                _Bubble(
                  text: '${data['text']}',
                  isUser: isUser,
                  time: timestamp,
                ),
              ],
            );
          },
        );
      },
    );
  }
}

class _AutoReplyNotice extends StatelessWidget {
  const _AutoReplyNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.md,
      ),
      color: AppColors.warning.withValues(alpha: 0.1),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline_rounded,
              size: AppIcons.sm, color: Color(0xFFB06000)),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'Balasan pada percakapan ini dibuat otomatis. Belum ada dokter yang '
              'membacanya. Untuk keadaan darurat, hubungi 119.',
              style: TextStyle(
                fontSize: 11.5,
                height: 1.4,
                color: AppColors.ink900.withValues(alpha: 0.75),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyConversation extends StatelessWidget {
  const _EmptyConversation(
      {required this.doctorName, required this.onSuggestion});

  final String doctorName;
  final ValueChanged<String> onSuggestion;

  static const _suggestions = [
    'Saya demam sejak 2 hari lalu',
    'Bagaimana cara verifikasi klaim BPJS?',
    'Apakah perlu kontrol ulang?',
  ];

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.xxxl),
      children: [
        const SizedBox(height: AppSpacing.xxl),
        Center(
          child: Container(
            width: 72,
            height: 72,
            decoration: const BoxDecoration(
              color: AppColors.brandSoft,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.forum_rounded,
                size: AppIcons.xl, color: AppColors.brandDark),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        Text(
          'Mulai percakapan dengan $doctorName',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: AppSpacing.sm),
        const Text(
          'Ceritakan keluhan Anda. Percakapan tersimpan dan dapat dibuka kembali.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 13, color: AppColors.ink500, height: 1.45),
        ),
        const SizedBox(height: AppSpacing.xxl),
        for (final suggestion in _suggestions)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: OutlinedButton(
              onPressed: () => onSuggestion(suggestion),
              child: Text(suggestion, textAlign: TextAlign.center),
            ),
          ),
      ],
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.text, required this.isUser, this.time});

  final String text;
  final bool isUser;
  final DateTime? time;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints:
            BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
        child: Container(
          margin: const EdgeInsets.only(bottom: AppSpacing.sm),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.md,
          ),
          decoration: BoxDecoration(
            color: isUser ? AppColors.brand : AppColors.white,
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(AppRadius.md),
              topRight: const Radius.circular(AppRadius.md),
              bottomLeft: Radius.circular(isUser ? AppRadius.md : 4),
              bottomRight: Radius.circular(isUser ? 4 : AppRadius.md),
            ),
            border: isUser ? null : Border.all(color: AppColors.ink100),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                text,
                style: TextStyle(
                  fontSize: 14,
                  height: 1.45,
                  color: isUser ? AppColors.white : AppColors.ink900,
                ),
              ),
              if (time != null) ...[
                const SizedBox(height: 4),
                Text(
                  DateFormat('HH:mm').format(time!.toLocal()),
                  style: TextStyle(
                    fontSize: 10,
                    color: isUser ? Colors.white70 : AppColors.ink500,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _DateSeparator extends StatelessWidget {
  const _DateSeparator({required this.date});

  final DateTime date;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final isToday =
        date.year == now.year && date.month == now.month && date.day == now.day;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: AppColors.ink100,
            borderRadius: BorderRadius.circular(AppRadius.pill),
          ),
          child: Text(
            isToday
                ? 'Hari ini'
                : DateFormat('dd MMMM yyyy', 'id_ID').format(date.toLocal()),
            style: const TextStyle(fontSize: 11, color: AppColors.ink500),
          ),
        ),
      ),
    );
  }
}

class _TypingIndicator extends StatelessWidget {
  const _TypingIndicator();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.only(
        left: AppSpacing.xl,
        bottom: AppSpacing.sm,
      ),
      alignment: Alignment.centerLeft,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(
                strokeWidth: 1.6, color: AppColors.ink300),
          ),
          const SizedBox(width: AppSpacing.sm),
          Text(
            'Menyiapkan balasan otomatis...',
            style: TextStyle(
              fontSize: 11.5,
              color: AppColors.ink900.withValues(alpha: 0.55),
            ),
          ),
        ],
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.focusNode,
    required this.sending,
    required this.onSend,
    required this.onQuickAction,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool sending;
  final VoidCallback onSend;
  final VoidCallback onQuickAction;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: const BoxDecoration(
          color: AppColors.white,
          border: Border(top: BorderSide(color: AppColors.ink100)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            IconButton(
              onPressed: onQuickAction,
              tooltip: 'Cek Gejala',
              icon: const Icon(Icons.medical_information_outlined,
                  color: AppColors.brandDark),
            ),
            Expanded(
              child: TextField(
                controller: controller,
                focusNode: focusNode,
                minLines: 1,
                maxLines: 5,
                textCapitalization: TextCapitalization.sentences,
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(
                  hintText: 'Tulis keluhan Anda...',
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.lg,
                    vertical: AppSpacing.md,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(AppRadius.pill),
                    borderSide: const BorderSide(color: AppColors.ink300),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(AppRadius.pill),
                    borderSide: const BorderSide(color: AppColors.ink300),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(AppRadius.pill),
                    borderSide:
                        const BorderSide(color: AppColors.brand, width: 1.6),
                  ),
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Material(
              color: AppColors.brand,
              shape: const CircleBorder(),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: sending ? null : onSend,
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: sending
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white),
                        )
                      : const Icon(Icons.send_rounded,
                          color: AppColors.white, size: 20),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
