"""Tests for transfer.py class."""
import sys
import unittest
from unittest.mock import patch, MagicMock

from transferpy.transfer import option_parse
from transferpy.Transferer import Transferer

from transferpy.test.utils import hide_stderr


class TestTransferer(unittest.TestCase):

    @patch('transferpy.Transferer.RemoteExecution')
    def setUp(self, executor_mock):
        self.executor = MagicMock()
        executor_mock.return_value = self.executor

        self.options = {'verbose': False}

        self.transferer = Transferer('source', 'path',
                                     ['target'], ['path'],
                                     self.options)

    def test_run_command(self):
        self.transferer.run_command('host', 'command')

        self.executor.run.assert_called_with('host', 'command')

    def test_is_dir(self):
        path = 'path'
        self.transferer.is_dir('host', path)

        args = self.executor.run.call_args[0]
        self.assertIn(r'"[ -d "{}" ]"'.format(path), args[1])

    def test_file_exists(self):
        file = 'path'
        self.transferer.file_exists('host', file)

        args = self.executor.run.call_args[0]
        self.assertIn(r'"[ -a "{}" ]"'.format(file), args[1])

    def test_calculate_checksum_for_dir(self):
        self.transferer.source_is_dir = True
        self.executor.run.return_value = MagicMock()
        self.executor.run.return_value.returncode = 0

        self.transferer.calculate_checksum('host', 'path')

        args = self.executor.run.call_args[0]
        self.assertIn('find', args[1][-1])
        self.assertIn('md5sum', args[1][-1])

    def test_calculate_checksum_for_file(self):
        self.transferer.source_is_dir = False
        self.executor.run.return_value = MagicMock()
        self.executor.run.return_value.returncode = 0

        self.transferer.calculate_checksum('host', 'path')

        args = self.executor.run.call_args[0]
        self.assertNotIn('find', args[1][-1])
        self.assertIn('md5sum', args[1][-1])

    def test_has_available_disk_space(self):
        self.executor.run.return_value = MagicMock()
        self.executor.run.return_value.returncode = 0

        size = 100
        self.executor.run.return_value.stdout = str(size + 1)

        result = self.transferer.has_available_disk_space('host', 'path', size)

        self.assertTrue(result)

    def test_disk_usage(self):
        self.executor.run.return_value = MagicMock()
        self.executor.run.return_value.returncode = 0
        size = 1024
        self.executor.run.return_value.stdout = "{} path".format(size)

        result = self.transferer.disk_usage('host', 'path')

        self.assertEqual(size, result)

    def test_compress_command_compressing(self):
        self.options['compress'] = True

        command = self.transferer.compress_command
        self.assertIn('pigz -c', command)

    def test_compress_command_not_compressing(self):
        self.options['compress'] = False

        self.transferer.source_is_dir = True
        command = self.transferer.compress_command
        self.assertEqual('', command)

        self.transferer.source_is_dir = False
        command = self.transferer.compress_command
        self.assertIn('cat', command)

    def test_decompress_command_compressing(self):
        self.options['compress'] = True

        command = self.transferer.decompress_command
        self.assertIn('pigz -c -d', command)

    def test_decompress_command_not_compressing(self):
        self.options['compress'] = False

        command = self.transferer.decompress_command
        self.assertEqual('', command)

    def test_encrypt_command_encrypting(self):
        self.options['encrypt'] = True

        command = self.transferer.encrypt_command
        self.assertIn('openssl enc', command)

    def test_encrypt_command_not_encrypting(self):
        self.options['encrypt'] = False

        command = self.transferer.encrypt_command
        self.assertEqual('', command)

    def test_decrypt_command_encrypting(self):
        self.options['encrypt'] = True

        command = self.transferer.decrypt_command
        self.assertIn('openssl enc -d', command)

    def test_decrypt_command_not_encrypting(self):
        self.options['encrypt'] = False

        command = self.transferer.decrypt_command
        self.assertEqual('', command)

    def test_parallel_checksum_source_and_target_command(self):
        """Test to check the parallel_checksum command"""
        self.options['parallel_checksum'] = False
        src_command = self.transferer.parallel_checksum_source_command
        trgt_command = self.transferer.parallel_checksum_target_command
        self.assertEqual('', src_command)
        self.assertEqual('', trgt_command)

        self.options['parallel_checksum'] = True
        src_command = self.transferer.parallel_checksum_source_command
        trgt_command = self.transferer.parallel_checksum_target_command
        self.assertEqual('| tee >(md5sum > {})'.format(
            self.transferer.parallel_checksum_source_path), src_command)
        self.assertEqual('| tee >(md5sum > {})'.format(
            self.transferer.parallel_checksum_target_path), trgt_command)

    def test_run_sanity_checks_failing(self):
        """Test case for Transferer.run function which simulates sanity check failure."""
        with patch.object(Transferer, 'sanity_checks') as mocked_sanity_check:
            mocked_sanity_check.side_effect = ValueError('Test sanity_checks')
            command = self.transferer.run()
            self.assertTrue(type(command) == list)

    def test_run_stoping_slave(self):
        """Test case for Transferer.run function which provides stop_slave option"""
        with patch.object(Transferer, 'sanity_checks') as mocked_sanity_check,\
                patch('transferpy.Transferer.MariaDB.stop_replication') as mocked_stop_replication:
            self.options['stop_slave'] = True
            #  Return value should be anything other than 0 for the if block to execute
            mocked_stop_replication.return_value = 1
            mocked_sanity_check.called_once()
            command = self.transferer.run()
            self.assertTrue(type(command) == list)

    def test_run_successfully(self):
        """Test case for Transferer.run function starting transfer successfully"""
        with patch.object(Transferer, 'sanity_checks') as mocked_sanity_check,\
                patch('transferpy.Transferer.Firewall.open') as mocked_open_firewall,\
                patch.object(Transferer, 'copy_to') as mocked_copy_to,\
                patch('transferpy.Transferer.Firewall.close') as mocked_close_firewall,\
                patch.object(Transferer, 'after_transfer_checks') as mocked_after_transfer_checks,\
                patch('transferpy.Transferer.MariaDB.start_replication') as mocked_start_replication:
            self.options['port'] = 4444
            mocked_copy_to.return_value = 0
            mocked_close_firewall.return_value = 0
            mocked_after_transfer_checks.return_value = 0
            mocked_start_replication.return_value = 0
            mocked_sanity_check.called_once()
            mocked_open_firewall.called_once()
            command = self.transferer.run()
            self.assertTrue(type(command) == list)

    def test_run_start_slave(self):
        """Test case for Transferer.run function for when it runs the
           start_slave function with the stop_slave option
        """
        with patch('transferpy.Transferer.MariaDB.stop_replication') as mocked_stop_replication,\
                patch.object(Transferer, 'sanity_checks') as mocked_sanity_check,\
                patch('transferpy.Transferer.Firewall.open') as mocked_open_firewall,\
                patch.object(Transferer, 'copy_to') as mocked_copy_to,\
                patch('transferpy.Transferer.Firewall.close') as mocked_close_firewall,\
                patch.object(Transferer, 'after_transfer_checks') as mocked_after_transfer_checks,\
                patch('transferpy.Transferer.MariaDB.start_replication') as mocked_start_replication:
            self.options['port'] = 4444
            self.options['stop_slave'] = True
            # We need to skip the first if statement
            # which checks the stop slave option
            mocked_stop_replication.return_value = 0
            mocked_copy_to.return_value = 0
            mocked_close_firewall.return_value = 0
            mocked_after_transfer_checks.return_value = 0
            # Return value should be anything other than 0
            # for this if block to execute
            mocked_start_replication.return_value = 1
            mocked_sanity_check.called_once()
            mocked_open_firewall.called_once()
            command = self.transferer.run()
            self.assertTrue(type(command) == list)

    def test_copy_to_success(self):
        """Test case for the successful run of Transferer.copy_to function"""
        self.options['compress'] = False
        self.options['parallel_checksum'] = False
        self.options['encrypt'] = False
        self.options['port'] = 4400
        with patch('transferpy.Transferer.time'):
            target_host = 'target'
            target_path = 'target_path'
            self.executor.run.return_value.returncode = 0
            returncode = self.transferer.copy_to(target_host, target_path)
            self.executor.start_job.assert_called_once()
            # Successful run should call the wait_job function
            self.executor.wait_job.assert_called_once()
            self.executor.kill_job.assert_not_called()
            self.assertEqual(returncode, 0)

    def test_copy_to_failure(self):
        """Test case for the failed run of Transferer.copy_to function"""
        self.options['compress'] = False
        self.options['parallel_checksum'] = False
        self.options['encrypt'] = False
        self.options['port'] = 4400
        with patch('transferpy.Transferer.time'):
            target_host = 'target'
            target_path = 'target_path'
            self.executor.run.return_value.returncode = 1
            returncode = self.transferer.copy_to(target_host, target_path)
            self.executor.start_job.assert_called_once()
            # Failure should call the kill_job function
            self.executor.kill_job.assert_called_once()
            self.executor.wait_job.assert_not_called()
            self.assertEqual(returncode, 1)

    def test_is_socket(self):
        """Test is_socket"""
        path = 'path'
        command = ['/bin/bash', '-c', r'"[ -S "{}" ]"'.format(path)]
        self.transferer.is_socket('source', path)
        self.executor.run.assert_called_once_with('source', command)

    def test_host_exists(self):
        """Test host_exists"""
        command = ['/bin/true']
        self.transferer.host_exists('source')
        self.executor.run.assert_called_once_with('source', command)

    def test_dir_is_empty(self):
        """Test dir_is_empty"""
        directory = 'dir'
        command = ['/bin/bash', '-c', r'"[ -z \"$(/bin/ls -A {})\" ]"'.format(directory)]
        self.transferer.dir_is_empty(directory, 'source')
        self.executor.run.assert_called_once_with('source', command)

    def test_parallel_checksum_source_command(self):
        """Test parallel_checksum_source_command"""
        self.options['parallel_checksum'] = True
        checksum_command = '| tee >(md5sum > {})'.format(self.transferer.parallel_checksum_source_path)
        self.assertEqual(checksum_command, self.transferer.parallel_checksum_source_command)
        # Make parallel_checksum False and try again
        self.options['parallel_checksum'] = False
        self.assertEqual('', self.transferer.parallel_checksum_source_command)

    def test_parallel_checksum_target_command(self):
        """Test parallel_checksum_target_command"""
        self.options['parallel_checksum'] = True
        checksum_command = '| tee >(md5sum > {})'.format(self.transferer.parallel_checksum_target_path)
        self.assertEqual(checksum_command, self.transferer.parallel_checksum_target_command)
        # Make parallel_checksum False and try again
        self.options['parallel_checksum'] = False
        self.assertEqual('', self.transferer.parallel_checksum_target_command)

    def test_read_checksum(self):
        """Test read_checksum"""
        path = 'path'
        command = ['/bin/bash', '-c', '/bin/cat < {}'.format(path)]
        self.executor.run.return_value.returncode = 0
        self.executor.run.return_value.stdout = "checksum - path"
        checksum = self.transferer.read_checksum('source', path)
        self.executor.run.assert_called_once_with('source', command)
        self.assertEqual(checksum, "checksum")

    def test_netcat_send_command(self):
        """Test netcat_send_command"""
        target_host = 'source'
        self.options['port'] = 4400
        expect_command = '| /bin/nc -q 0 -w 300 {} {}'.format(target_host, self.options['port'])
        actual_command = self.transferer.netcat_send_command(target_host)
        self.assertEqual(expect_command, actual_command)

    def test_netcat_listen_command(self):
        """Test netcat_listen_command"""
        self.options['port'] = 4400
        expect_command = '/bin/nc -l -w 300 -p {}'.format(self.options['port'])
        actual_command = self.transferer.netcat_listen_command
        self.assertEqual(expect_command, actual_command)

    def test_tar_command(self):
        """Test tar_command"""
        expected_command = '/bin/tar cf -'
        actual_command = self.transferer.tar_command
        self.assertEqual(expected_command, actual_command)

    def test_untar_command(self):
        """Test untar_command"""
        expected_command_decompress = '| /bin/tar --strip-components=1 -xf -'
        expected_command_file = '| /bin/tar xf -'
        self.options['type'] = 'decompress'
        actual_command = self.transferer.untar_command
        self.assertEqual(actual_command, expected_command_decompress)
        self.options['type'] = 'file'
        actual_command = self.transferer.untar_command
        self.assertEqual(actual_command, expected_command_file)

    def test_get_datadir_from_socket(self):
        """Test get_datadir_from_socket"""
        socket = 'mysqld.sock'
        datadir = '/srv/sqldata'
        actual_dir = self.transferer.get_datadir_from_socket(socket)
        self.assertEqual(datadir, actual_dir)
        socket = 'test.mysqld.s1.sock'
        datadir = '/srv/sqldata.s1'
        actual_dir = self.transferer.get_datadir_from_socket(socket)
        self.assertEqual(datadir, actual_dir)
        # Give wrong socket input
        socket = 'test.mysqld.smx1.sock'
        with self.assertRaises(Exception):
            self.transferer.get_datadir_from_socket(socket)

    def test_xtrabackup_command(self):
        """Test xtrabackup_command"""
        self.transferer.source_path = 'mysqld.sock'
        socket = self.transferer.source_path
        datadir = self.transferer.get_datadir_from_socket(socket)
        expected_command = 'xtrabackup --backup --target-dir /tmp ' \
                           '--user {} --socket={} --close-files --datadir={} --parallel={} ' \
                           '--stream=xbstream --slave-info --skip-ssl'.\
            format('root', socket, datadir, 16)
        actual_command = self.transferer.xtrabackup_command
        self.assertEqual(expected_command, actual_command)

    def test_mbstream_command(self):
        """Test mbstream_command"""
        expected_command = '| mbstream -x'
        actual_command = self.transferer.mbstream_command
        self.assertEqual(expected_command, actual_command)

    def test_password(self):
        """Test password function"""
        self.transferer._password = None
        password = self.transferer.password
        self.assertNotEqual(password, None)
        self.transferer._password = 'password'
        password = self.transferer.password
        self.assertEqual('password', password)

    def test_sanity_checks_file(self):
        """Test sanity_checks for file/dir"""
        with patch.object(Transferer, 'host_exists') as mocked_host_exists, \
                patch.object(Transferer, 'disk_usage') as mocked_disk_usage, \
                patch.object(Transferer, 'file_exists') as mocked_file_exists, \
                patch.object(Transferer, 'has_available_disk_space') as mocked_disk_space, \
                patch.object(Transferer, 'is_socket') as mocked_is_socket, \
                patch.object(Transferer, 'calculate_checksum') as mocked_calculate_checksum:
            self.transferer.target_hosts = ['target']
            self.transferer.target_paths = ['path']
            self.options['checksum'] = True
            self.options['type'] = 'file'
            mocked_disk_space.return_value = True
            mocked_is_socket.return_value = False
            mocked_file_exists.side_effect = [True, True, False]
            mocked_host_exists.return_value.returncode = 0
            self.transferer.sanity_checks()
            self.assertEqual(mocked_host_exists.call_count, 2)
            mocked_disk_space.assert_called_once()
            mocked_disk_usage.assert_called_once()
            mocked_calculate_checksum.assert_called_once()
            self.assertEqual(mocked_file_exists.call_count, 3)

    def test_sanity_checks_xtrabackup(self):
        """Test sanity_checks for xtrabackup/decompress"""
        with patch.object(Transferer, 'host_exists') as mocked_host_exists, \
                patch.object(Transferer, 'disk_usage') as mocked_disk_usage, \
                patch.object(Transferer, 'file_exists') as mocked_file_exists, \
                patch.object(Transferer, 'dir_is_empty') as mocked_dir_is_empty, \
                patch.object(Transferer, 'has_available_disk_space') as mocked_disk_space, \
                patch.object(Transferer, 'is_socket') as mocked_is_socket, \
                patch.object(Transferer, 'calculate_checksum') as mocked_calculate_checksum:
            self.transferer.target_hosts = ['target']
            self.transferer.target_paths = ['path']
            self.options['checksum'] = True
            self.options['type'] = 'xtrabackup'
            mocked_dir_is_empty.return_value = True
            mocked_disk_space.return_value = True
            mocked_is_socket.return_value = True
            mocked_file_exists.return_value = True
            mocked_host_exists.return_value.returncode = 0
            self.transferer.sanity_checks()
            mocked_dir_is_empty.assert_called_once()
            self.assertEqual(mocked_host_exists.call_count, 2)
            mocked_disk_space.assert_called_once()
            mocked_disk_usage.assert_called_once()
            mocked_is_socket.assert_called_once()
            mocked_calculate_checksum.assert_called_once()
            self.assertEqual(mocked_file_exists.call_count, 2)

    def test_after_transfer_checks(self):
        """Test after_transfer_checks"""
        with patch.object(Transferer, 'disk_usage') as mocked_disk_usage, \
                patch.object(Transferer, 'file_exists') as mocked_file_exists, \
                patch.object(Transferer, 'calculate_checksum') as mocked_calculate_checksum, \
                patch.object(Transferer, 'read_checksum') as mocked_read_checksum:
            target_host = 'target'
            target_path = 'path'
            self.options['checksum'] = True
            self.options['parallel_checksum'] = True
            self.options['type'] = 'file'
            self.transferer.checksum = 'checksum'
            mocked_calculate_checksum.return_value = 'checksum'
            mocked_file_exists.return_value = True
            result = self.transferer.after_transfer_checks(0, target_host, target_path)
            mocked_disk_usage.assert_called_once()
            mocked_calculate_checksum.assert_called_once()
            mocked_file_exists.assert_called_once()
            self.assertEqual(mocked_read_checksum.call_count, 2)
            self.assertEqual(result, 0)


class TestArgumentParsing(unittest.TestCase):
    """Test cases for the command line arguments parsing."""

    def option_parse(self, args):
        """Call parse_args patching the arguments."""
        with patch.object(sys, 'argv', args):
            return option_parse()

    def check_bad_args(self, args, expected_error=SystemExit):
        """Check arg parsing fails for the given args."""
        with self.assertRaises(expected_error) as exc:
            with hide_stderr():
                self.option_parse(args)

        if expected_error == SystemExit:
            self.assertEquals(exc.exception.code, 2)

    def test_missing_required_args(self):
        """Test errors with missing required args."""
        missing_required_args_list = [
            ['transfer'],
            ['transfer', 'src:path'],
            ['transfer', 'trg?:path'],
        ]
        for test_args in missing_required_args_list:
            self.check_bad_args(test_args)

    def test_bad_source(self):
        """Test errors with the source."""
        test_args = ['transfer', 'source', 'target:path']
        self.check_bad_args(test_args)

    def test_bad_target(self):
        """Test errors with the target."""
        test_args = ['transfer', 'source:path', 'target']
        self.check_bad_args(test_args)

    def test_just_source_and_targets(self):
        """Test call with just source and targets."""
        src = 'source'
        src_path = 'source_path'
        trg1 = 'target1'
        trg1_path = 'dst_path1'
        trg2 = 'target2'
        trg2_path = 'dst_path2'
        test_args = ['transfer',
                     '{}:{}'.format(src, src_path),
                     '{}:{}'.format(trg1, trg1_path),
                     '{}:{}'.format(trg2, trg2_path)]
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(test_args)

        self.assertEqual(src, source_host)
        self.assertEqual(src_path, source_path)
        self.assertEqual([trg1, trg2], target_hosts)
        self.assertEqual([trg1_path, trg2_path], target_paths)
        self.assertEqual(other_options['port'], 0)
        self.assertTrue(other_options['compress'])
        self.assertTrue(other_options['encrypt'])

    def test_port(self):
        """Test port param."""
        port = 12345
        test_args = ['transfer', 'source:path', 'target:path', '--port', str(port)]
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(test_args)
        self.assertEqual(other_options['port'], port)
        self.assertTrue(other_options['compress'])
        self.assertTrue(other_options['encrypt'])

    def test_compress(self):
        """Test compress params."""
        base_args = ['transfer', 'source:path', 'target:path']

        compress_test_args = base_args + ['--compress']
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(compress_test_args)
        self.assertTrue(other_options['compress'])
        self.assertTrue(other_options['encrypt'])

        no_compress_test_args = base_args + ['--no-compress']
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(no_compress_test_args)
        self.assertFalse(other_options['compress'])
        self.assertTrue(other_options['encrypt'])

    def test_encrypt(self):
        """Test encrypt params."""
        base_args = ['transfer', 'source:path', 'target:path']

        encrypt_test_args = base_args + ['--encrypt']
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(encrypt_test_args)
        self.assertTrue(other_options['compress'])
        self.assertTrue(other_options['encrypt'])

        no_encrypt_test_args = base_args + ['--no-encrypt']
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(no_encrypt_test_args)
        self.assertTrue(other_options['compress'])
        self.assertFalse(other_options['encrypt'])

    def test_parallel_checksum(self):
        """Test parallel-checksum param."""
        base_args = ['transfer', 'source:path', 'target:path']
        # By default, normal checksum is enabled. So, irrespective of the
        # --parallel-checksum argument, this option is disabled.
        parallel_checksum_test_args = base_args + ['--parallel-checksum']
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(parallel_checksum_test_args)
        self.assertTrue(other_options['checksum'])
        self.assertFalse(other_options['parallel_checksum'])

        no_parallel_checksum_test_args = base_args + ['--no-parallel-checksum']
        (source_host, source_path, target_hosts, target_paths, other_options)\
            = self.option_parse(no_parallel_checksum_test_args)
        self.assertTrue(other_options['checksum'])
        self.assertFalse(other_options['parallel_checksum'])

        # Now disable the normal checksum so that parallel-checksum can take effect
        base_args = ['transfer', 'source:path', 'target:path', '--no-checksum']
        # By default, normal checksum is enabled. So, irrespective of the
        # --parallel-checksum argument, this option is disabled.
        parallel_checksum_test_args = base_args + ['--parallel-checksum']
        (source_host, source_path, target_hosts, target_paths, other_options) \
            = self.option_parse(parallel_checksum_test_args)
        self.assertFalse(other_options['checksum'])
        self.assertTrue(other_options['parallel_checksum'])

        no_parallel_checksum_test_args = base_args + ['--no-parallel-checksum']
        (source_host, source_path, target_hosts, target_paths, other_options) \
            = self.option_parse(no_parallel_checksum_test_args)
        self.assertFalse(other_options['checksum'])
        self.assertFalse(other_options['parallel_checksum'])
