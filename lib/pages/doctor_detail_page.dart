import 'package:flutter/material.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:intl/intl.dart';

class DoctorDetailPage extends StatefulWidget {
  const DoctorDetailPage({super.key, required this.doctor});

  final Map<String, dynamic> doctor;

  @override
  State<DoctorDetailPage> createState() => _DoctorDetailPageState();
}

class _DoctorDetailPageState extends State<DoctorDetailPage> {
  static const _slots = ['09:00', '10:00', '11:00', '14:00', '15:00', '16:00'];

  late final List<DateTime> _days;
  DateTime? _selectedDay;
  String? _selectedSlot;

  @override
  void initState() {
    super.initState();
    final today = DateTime.now();

    _days = List.generate(
      7,
      (i) =>
          DateTime(today.year, today.month, today.day).add(Duration(days: i)),
    );
    _selectedDay = _days.first;
  }

  bool get _canSubmit => _selectedDay != null && _selectedSlot != null;

  bool _slotAvailable(String slot) {
    final day = _selectedDay;
    if (day == null) return false;
    final now = DateTime.now();
    final isToday =
        day.year == now.year && day.month == now.month && day.day == now.day;
    if (!isToday) return true;
    final hour = int.parse(slot.split(':').first);
    return hour > now.hour;
  }

  void _submit() {
    final day = DateFormat('EEEE, dd MMMM yyyy', 'id_ID').format(_selectedDay!);
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.event_busy_rounded,
            color: AppColors.warning, size: 40),
        title: const Text('Belum dapat diproses'),
        content: Text(
          'Anda memilih $day pukul $_selectedSlot dengan ${widget.doctor['name']}.\n\n'
          'Penjadwalan janji temu belum terhubung ke sistem fasilitas kesehatan, '
          'sehingga permintaan ini belum tersimpan. Silakan hubungi faskes Anda '
          'secara langsung.',
          style: const TextStyle(height: 1.5),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Mengerti'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final doctor = widget.doctor;

    return Scaffold(
      appBar: AppBar(title: Text('${doctor['name']}')),
      body: ListView(
        padding: EdgeInsets.zero,
        children: [
          _header(context, doctor),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(AppSpacing.page),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const AppSectionHeader(title: 'Pilih Tanggal'),
                SizedBox(
                  height: 78,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: _days.length,
                    separatorBuilder: (_, __) =>
                        const SizedBox(width: AppSpacing.sm),
                    itemBuilder: (context, index) => _dayChip(_days[index]),
                  ),
                ),
                const SizedBox(height: AppSpacing.xxl),
                const AppSectionHeader(title: 'Pilih Jam'),
                Wrap(
                  spacing: AppSpacing.md,
                  runSpacing: AppSpacing.md,
                  children: _slots.map(_slotChip).toList(),
                ),
                const SizedBox(height: AppSpacing.lg),
                if (!_canSubmit)
                  const Text(
                    'Pilih tanggal dan jam untuk melanjutkan.',
                    style: TextStyle(fontSize: 12.5, color: AppColors.ink500),
                  ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.page),
          child: FilledButton(
            onPressed: _canSubmit ? _submit : null,
            child: const Text('Buat Janji Temu'),
          ),
        ),
      ),
    );
  }

  Widget _header(BuildContext context, Map<String, dynamic> doctor) {
    final name = '${doctor['name']}';
    return Container(
      padding: const EdgeInsets.all(AppSpacing.page),
      color: AppColors.white,
      child: Row(
        children: [
          CircleAvatar(
            radius: 40,
            backgroundColor: AppColors.brandSoft,
            child: Text(
              name
                  .replaceAll(RegExp(r'^Dr\.?\s*'), '')
                  .substring(0, 2)
                  .toUpperCase(),
              style: const TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.w700,
                color: AppColors.brandDark,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 18),
                ),
                const SizedBox(height: 4),
                Text(
                  '${doctor['specialty']}',
                  style: const TextStyle(color: AppColors.ink500, fontSize: 14),
                ),
                const SizedBox(height: AppSpacing.sm),
                Row(
                  children: [
                    const Icon(Icons.star_rounded,
                        color: AppColors.warning, size: AppIcons.sm),
                    const SizedBox(width: 4),
                    Text(
                      '${doctor['rating']}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w600, fontSize: 13.5),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _dayChip(DateTime day) {
    final selected = _selectedDay != null &&
        _selectedDay!.day == day.day &&
        _selectedDay!.month == day.month;

    return GestureDetector(
      onTap: () => setState(() {
        _selectedDay = day;

        if (_selectedSlot != null && !_slotAvailable(_selectedSlot!)) {
          _selectedSlot = null;
        }
      }),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 62,
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
        decoration: BoxDecoration(
          color: selected ? AppColors.brand : AppColors.white,
          borderRadius: AppRadius.smAll,
          border:
              Border.all(color: selected ? AppColors.brand : AppColors.ink300),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              DateFormat('EEE', 'id_ID').format(day),
              style: TextStyle(
                fontSize: 11.5,
                color: selected ? Colors.white70 : AppColors.ink500,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '${day.day}',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: selected ? AppColors.white : AppColors.ink900,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _slotChip(String slot) {
    final available = _slotAvailable(slot);
    final selected = _selectedSlot == slot;

    return ChoiceChip(
      label: Text(slot),
      selected: selected,
      onSelected:
          available ? (_) => setState(() => _selectedSlot = slot) : null,
      showCheckmark: false,
      labelStyle: TextStyle(
        fontWeight: FontWeight.w600,
        color: !available
            ? AppColors.ink300
            : (selected ? AppColors.brandDark : AppColors.ink900),
      ),
      side: BorderSide(color: selected ? AppColors.brand : AppColors.ink300),
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md),
    );
  }
}
